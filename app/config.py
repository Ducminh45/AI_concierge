from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import Field, field_validator
import secrets


class Settings(BaseSettings):
    """Central configuration for the AI Resort Concierge 24/7.

    Uses environment variables with the prefix `RC_` (Resort Concierge).
    """

    model_config = SettingsConfigDict(
        env_prefix="RC_", env_file=".env", extra="ignore"
    )

    # App
    app_name: str = "AI Resort Concierge 24/7"
    environment: str = Field(default="dev", description="dev|staging|prod")
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Resort Info
    resort_name: str = "Vietnam Luxury Resorts"
    default_language: str = "vi"
    resort_timezone: str = "Asia/Ho_Chi_Minh"

    # Database (SQLite by default, set to postgresql://... for Postgres)
    database_url: str = Field(default="sqlite:///./resort_concierge.db")

    # Redis (optional caching / agent messaging layer)
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and agent messaging",
    )
    redis_enabled: bool = Field(
        default=False,
        description="Enable Redis-backed caching (falls back to in-memory TTL cache when disabled)",
    )

    # RAG
    rag_collection: str = "resort_concierge_knowledge"
    rag_persist_dir: str = "./.rag_store"
    rag_max_results: int = 5

    # LLM / Embeddings (optional)
    openai_api_key: str | None = Field(
        default=None, description="Optional. If absent, mock responses are used."
    )
    openai_model: str = "gpt-4o-mini"
    openai_embeddings_model: str = "text-embedding-3-small"
    openai_max_tokens: int = Field(default=4096, description="Max tokens for OpenAI completions")

    # Anthropic
    anthropic_api_key: str | None = Field(default=None, description="Anthropic API key")
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenRouter (OpenAI-compatible gateway)
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_enabled: bool = False
    openrouter_max_tokens: int = Field(default=4096, description="Max tokens for OpenRouter completions")

    # Ollama (local models)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_enabled: bool = False

    # LLM Routing
    llm_provider_priority: str = Field(
        default="openai,anthropic,openrouter,ollama",
        description="Comma-separated provider priority, e.g. 'openai,anthropic,openrouter,ollama'",
    )
    llm_fallback_enabled: bool = True

    # Hallucination Detection
    hallucination_high_threshold: float = 0.7
    hallucination_medium_threshold: float = 0.4

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_experiment_name: str = "resort-concierge"
    mlflow_enabled: bool = False

    # Security
    api_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="API key for authentication",
    )
    jwt_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT secret key for token signing",
    )
    rate_limit_per_minute: int = 60

    # RAG Ingestion Security
    rag_ingestion_token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Token required for RAG ingestion operations",
    )

    # Weather API (OpenWeatherMap)
    weather_api_key: str = Field(
        default="6f1b7c5bee037d2097dd5c189ae6ea39",
        description="API key for OpenWeatherMap current weather API",
    )

    # PDFs
    pdf_output_dir: str = "./generated_pdfs"

    # Misc
    enable_gradio: bool = False

    # Embedding model
    embedding_model: str = "all-MiniLM-L6-v2"

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        allowed = ["dev", "test", "staging", "prod", "production"]
        if v not in allowed:
            raise ValueError(f"Invalid environment: {v}. Must be one of {allowed}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        allowed = [
            "debug",
            "info",
            "warning",
            "error",
            "critical",
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]
        if v.lower() not in [a.lower() for a in allowed]:
            raise ValueError(f"Invalid log level: {v}. Must be one of {allowed}")
        return v

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def validate_openai_api_key(cls, v, info):
        env = info.data.get("environment", "dev")
        if env in ["prod", "production", "staging"] and (not v or v == "sk-..."):
            raise ValueError(
                "OPENAI_API_KEY must be set in production/staging environments."
            )
        return v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key_strength(cls, v, info):
        env = info.data.get("environment", "dev")
        # In dev, auto-generate is fine
        if env == "dev":
            return v
        # In prod, must be explicitly set and strong
        if env in ["prod", "production", "staging"]:
            if not v or len(v) < 32:
                raise ValueError(
                    "API_KEY must be explicitly set and at least 32 characters in production"
                )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
