from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth.security import APIKeyManager
from .config import get_settings
from .core.guardrails import InputGuard
from .core.llm_providers import (
    AnthropicProvider,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    ModelRouter,
    OllamaProvider,
    OpenAIProvider,
)
from .core.memory import MemoryStore
from .core.orchestrator import ConciergeOrchestrator
from .core.tools import make_registry
from .core.vinpearl_search import VinpearlTavilySearch
from .database.db import DatabaseManager
from .monitoring.metrics import install_metrics
from .rag.vector_rag import VectorRAG


class MockLLMProvider(LLMProvider):
    """Local fallback used when no provider API key is configured."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def supports_response_format(self) -> bool:
        return True

    def translate_tool_schemas(self, openai_schemas: list[dict]) -> list[dict]:
        return openai_schemas

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
    ) -> LLMResponse:
        if response_format and response_format.get("type") == "json_object":
            return LLMResponse(
                content='{"intent":"chitchat","reasoning":"mock provider"}',
                model="mock",
                provider=self.name,
            )

        user_text = ""
        for message in reversed(messages):
            if message.role == "user":
                user_text = message.content
                break

        return LLMResponse(
            content=(
                "Xin chào, tôi là trợ lý concierge 24/7. "
                "Tôi đã ghi nhận yêu cầu của quý khách."
                if user_text
                else "Xin chào, tôi có thể hỗ trợ gì cho quý khách?"
            ),
            model="mock",
            provider=self.name,
        )


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default")


def _build_llm_provider(settings) -> LLMProvider:
    providers: list[LLMProvider] = []

    if settings.openai_api_key:
        providers.append(
            OpenAIProvider(
                settings.openai_api_key,
                model=settings.openai_model,
                max_tokens=settings.openai_max_tokens,
            )
        )
    if settings.anthropic_api_key:
        providers.append(
            AnthropicProvider(
                settings.anthropic_api_key,
                model=settings.anthropic_model,
            )
        )
    if settings.openrouter_enabled and settings.openrouter_api_key:
        providers.append(
            OpenAIProvider(
                settings.openrouter_api_key,
                model=settings.openrouter_model,
                base_url="https://openrouter.ai/api/v1",
                max_tokens=settings.openrouter_max_tokens,
            )
        )
    if settings.ollama_enabled:
        providers.append(
            OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )
        )

    if not providers:
        return MockLLMProvider()
    if len(providers) == 1:
        return providers[0]
    return ModelRouter(providers, fallback_enabled=settings.llm_fallback_enabled)


def _serialise_optional(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _ensure_knowledge_ingested(
    rag,
    settings,
    knowledge_folder: str = "./data/knowledge",
) -> int:
    if rag.collection.count() > 0:
        return 0

    folder = Path(knowledge_folder)
    if not folder.exists():
        return 0

    return rag.ingest_folder(
        str(folder),
        token=settings.rag_ingestion_token,
    )


def _configure_state(app: FastAPI) -> None:
    if hasattr(app.state, "db"):
        return

    settings = get_settings()
    db = DatabaseManager(settings)
    rag = VectorRAG(
        settings.rag_persist_dir,
        settings.rag_collection,
        embedding_model=settings.embedding_model,
        ingestion_token=settings.rag_ingestion_token,
    )
    _ensure_knowledge_ingested(rag, settings)
    vinpearl_domains = tuple(
        domain.strip().lower()
        for domain in settings.tavily_include_domains.split(",")
        if domain.strip()
    )
    web_search = VinpearlTavilySearch(
        api_key=settings.tavily_api_key,
        base_url=settings.tavily_base_url,
        include_domains=vinpearl_domains or ("vinpearl.com",),
        max_results=settings.tavily_max_results,
        timeout_seconds=settings.tavily_timeout_seconds,
    )
    registry = make_registry(
        db=db,
        rag_search_fn=lambda query, k=5: rag.search(query, k),
        vinpearl_web_search_fn=web_search.search,
    )
    memory = MemoryStore(db=db)
    llm = _build_llm_provider(settings)

    app.state.settings = settings
    app.state.db = db
    app.state.rag = rag
    app.state.tool_registry = registry
    app.state.api_key_manager = APIKeyManager(db)
    app.state.orchestrator = ConciergeOrchestrator(
        llm_provider=llm,
        rag=rag,
        tool_registry=registry,
        memory_store=memory,
        input_guard=InputGuard(),
        web_search=web_search,
    )


def build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _configure_state(app)
        yield

    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    install_metrics(app)

    @app.middleware("http")
    async def ensure_app_state(request, call_next):
        _configure_state(request.app)
        return await call_next(request)

    from .api.admin_routes import router as admin_router
    from .api.service_routes import router as service_router
    from .api.user_routes import router as user_router

    app.include_router(admin_router)
    app.include_router(service_router)
    app.include_router(user_router)

    @app.get("/health")
    async def health():
        active_settings = getattr(app.state, "settings", settings)
        return {
            "ok": True,
            "app": active_settings.app_name,
            "environment": active_settings.environment,
        }

    @app.get("/tools")
    async def tools():
        registry = app.state.tool_registry
        return {
            "ok": True,
            "tools": [
                {"name": tool.name, "description": tool.description}
                for tool in registry.list()
            ],
        }

    @app.post("/chat")
    async def chat(body: ChatRequest):
        result = await app.state.orchestrator.handle(
            body.message,
            body.session_id,
        )
        return {
            "ok": True,
            "reply": result.response,
            "plan": result.plan.model_dump(),
            "tool_result": result.tool_result,
            "sources": result.sources,
            "confidence": _serialise_optional(result.confidence),
            "claim_verification": _serialise_optional(result.claim_verification),
            "guardrail": result.guardrail,
            "pii_types": result.pii_types,
        }

    @app.post("/chat/stream")
    async def chat_stream(body: ChatRequest):
        response = await chat(body)

        async def stream():
            yield response["reply"]

        return StreamingResponse(stream(), media_type="text/plain")

    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/css", StaticFiles(directory=frontend_dir / "css"), name="css")
        app.mount("/js", StaticFiles(directory=frontend_dir / "js"), name="js")

        @app.get("/")
        async def index():
            return FileResponse(frontend_dir / "index.html")

    return app


app = build_app()
