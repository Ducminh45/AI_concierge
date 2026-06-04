from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core.llm_providers import LLMMessage, LLMResponse, LLMToolCall
from app.core.orchestrator import ConciergeOrchestrator, IntentType, Plan
from app.core.guardrails import InputGuard
from app.core.prompt_loader import load_prompt
from app.core.tools import ToolRegistry


class FakeReActProvider:
    supports_response_format = False
    name = "fake-react"

    def __init__(self):
        self.calls: list[dict] = []

    def translate_tool_schemas(self, openai_schemas):
        return openai_schemas

    async def chat(self, messages, tools=None, model=None, response_format=None):
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "response_format": response_format,
        })
        if len(self.calls) == 1:
            return LLMResponse(
                content="Thought: I need resort knowledge.\nAction: search_amenities",
                tool_calls=[
                    LLMToolCall(
                        id="call-1",
                        name="search_amenities",
                        arguments=json.dumps({"query": "spa hours"}),
                    )
                ],
                usage={"total_tokens": 5},
            )
        return LLMResponse(
            content="Final Answer: The spa is open from 9 AM to 9 PM.",
            usage={"total_tokens": 7},
        )


def _memory():
    class Memory:
        def __init__(self):
            self.saved = []

        def get_messages(self, session_id, limit=5):
            return []

        def add_message(self, session_id, role, content):
            self.saved.append((session_id, role, content))

    return Memory()


def test_system_prompts_define_vinpearl_travel_scope_and_refusals():
    planner_prompt = load_prompt(
        "planner",
        tool_list="search_amenities: Search resort knowledge",
        today_date="2026-06-04",
    )
    agent_prompt = load_prompt(
        "executor.agent",
        tools="search_amenities",
        history="",
        question="What can I do at Vinpearl Phu Quoc?",
    )

    combined = f"{planner_prompt}\n{agent_prompt}"

    assert "specialized chatbot for Vinpearl Travel only" in combined
    assert "You must not answer questions outside Vinpearl Travel" in combined
    assert "General travel advice not related to Vinpearl" in combined
    assert (
        "Xin lỗi, mình chỉ có thể hỗ trợ các câu hỏi liên quan đến Vinpearl Travel"
        in combined
    )
    assert "Sorry, I can only help with Vinpearl Travel questions" in combined


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Viết giúp mình một đoạn code Python sắp xếp danh sách",
            "Xin lỗi, mình chỉ có thể hỗ trợ các câu hỏi liên quan đến Vinpearl Travel",
        ),
        (
            "Can you explain my school homework?",
            "Sorry, I can only help with Vinpearl Travel questions",
        ),
    ],
)
async def test_handle_refuses_out_of_scope_with_vinpearl_travel_message(
    message,
    expected,
):
    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=ToolRegistry(),
        memory_store=_memory(),
        input_guard=InputGuard(),
    )

    result = await orch.handle(message, "session-1")

    assert result.guardrail == "off_topic"
    assert result.response.startswith(expected)


@pytest.mark.asyncio
async def test_tool_intent_runs_react_loop_with_tool_observation():
    provider = FakeReActProvider()
    registry = ToolRegistry()
    seen_queries: list[str] = []

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        seen_queries.append(query)
        return {"ok": True, "answer": "The spa is open from 9 AM to 9 PM."}

    orch = ConciergeOrchestrator(
        llm_provider=provider,
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
    )

    result = await orch._execute_tool(
        Plan(intent=IntentType.TOOL, tool_name="search_amenities"),
        "What are the spa hours?",
        "session-1",
    )

    assert seen_queries == ["spa hours"]
    assert len(provider.calls) == 2
    assert provider.calls[0]["tools"][0]["function"]["name"] == "search_amenities"
    system_prompt = provider.calls[0]["messages"][0].content
    assert "Thought" in system_prompt
    assert "Action" in system_prompt
    assert "Observation" in system_prompt
    assert "Final Answer" in system_prompt
    assert "do not invent" in system_prompt.lower()
    second_messages = provider.calls[1]["messages"]
    assert any(
        message.role == "tool"
        and message.tool_call_id == "call-1"
        and "9 AM to 9 PM" in message.content
        for message in second_messages
    )
    assert result.response == "Final Answer: The spa is open from 9 AM to 9 PM."
    assert result.tool_result == {
        "search_amenities": {"ok": True, "answer": "The spa is open from 9 AM to 9 PM."}
    }
    assert result.rag_contexts == [
        '{"ok": true, "answer": "The spa is open from 9 AM to 9 PM."}'
    ]


@pytest.mark.asyncio
async def test_react_loop_reports_unknown_tool_as_observation_not_execution():
    class UnknownToolProvider(FakeReActProvider):
        async def chat(self, messages, tools=None, model=None, response_format=None):
            self.calls.append({"messages": messages, "tools": tools})
            if len(self.calls) == 1:
                return LLMResponse(
                    content="Thought: I should use a tool.",
                    tool_calls=[
                        LLMToolCall(
                            id="bad-call",
                            name="invented_tool",
                            arguments="{}",
                        )
                    ],
                )
            return LLMResponse(
                content="Final Answer: I do not have a supported tool for that.",
            )

    provider = UnknownToolProvider()
    registry = ToolRegistry()
    orch = ConciergeOrchestrator(
        llm_provider=provider,
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
    )

    result = await orch._execute_tool(
        Plan(intent=IntentType.TOOL),
        "Can you do an unsupported action?",
        "session-1",
    )

    assert len(provider.calls) == 2
    assert any(
        message.role == "tool"
        and message.tool_call_id == "bad-call"
        and "Unknown tool" in message.content
        for message in provider.calls[1]["messages"]
    )
    assert result.response == "Final Answer: I do not have a supported tool for that."


@pytest.mark.asyncio
async def test_handle_routes_resort_question_through_agentic_tool_loop_not_direct_rag():
    class PlanningProvider(FakeReActProvider):
        supports_response_format = True

        async def chat(self, messages, tools=None, model=None, response_format=None):
            self.calls.append({
                "messages": messages,
                "tools": tools,
                "response_format": response_format,
            })
            if response_format == {"type": "json_object"}:
                return LLMResponse(
                    content=json.dumps({
                        "intent": "tool",
                        "tool_name": "search_amenities",
                        "tool_args": {},
                        "search_query": None,
                        "reasoning": "Use resort knowledge search as a tool.",
                    }),
                )
            if len([call for call in self.calls if call["tools"]]) == 1:
                return LLMResponse(
                    content="Thought: I need verified resort knowledge.",
                    tool_calls=[
                        LLMToolCall(
                            id="call-spa",
                            name="search_amenities",
                            arguments=json.dumps({"query": "spa hours"}),
                        )
                    ],
                )
            return LLMResponse(
                content="Final Answer: The spa is open from 9 AM to 9 PM.",
            )

    class NoDirectRAG:
        def search(self, query, k=5):
            raise AssertionError("RAG should be reached through a tool, not direct chatbot path")

    provider = PlanningProvider()
    registry = ToolRegistry()

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        return {"ok": True, "answer": "The spa is open from 9 AM to 9 PM."}

    orch = ConciergeOrchestrator(
        llm_provider=provider,
        rag=NoDirectRAG(),
        tool_registry=registry,
        memory_store=_memory(),
    )

    result = await orch.handle("What are the spa hours?", "session-1")

    assert result.plan.intent == IntentType.TOOL
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert provider.calls[1]["tools"][0]["function"]["name"] == "search_amenities"
    assert result.response == "Final Answer: The spa is open from 9 AM to 9 PM."


@pytest.mark.asyncio
async def test_plan_repairs_bare_vinpearl_entity_clarify_to_knowledge_tool():
    class ClarifyProvider(FakeReActProvider):
        supports_response_format = True

        async def chat(self, messages, tools=None, model=None, response_format=None):
            self.calls.append({
                "messages": messages,
                "tools": tools,
                "response_format": response_format,
            })
            return LLMResponse(
                content=json.dumps({
                    "intent": "clarify",
                    "tool_name": None,
                    "tool_args": {},
                    "search_query": None,
                    "reasoning": "The user did not ask a specific question.",
                }),
            )

    registry = ToolRegistry()

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        return {"ok": True, "results": []}

    orch = ConciergeOrchestrator(
        llm_provider=ClarifyProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
    )

    plan = await orch.plan("Vinpearl Phu Quoc", "session-1")

    assert plan.intent == IntentType.TOOL
    assert plan.tool_name == "search_amenities"
    assert plan.tool_args == {"query": "Vinpearl Phu Quoc"}


@pytest.mark.asyncio
async def test_search_amenities_empty_result_falls_back_to_tavily_for_vinpearl_query():
    registry = ToolRegistry()

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        return {"ok": True, "query": query, "results": []}

    web_search = AsyncMock()
    web_search.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Vinpearl Phú Quốc nằm tại Bãi Dài, Gành Dầu, Phú Quốc.",
                "source": "https://vinpearl.com/vi/hotels-phu-quoc",
            }
        ],
    }
    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
        web_search=web_search,
    )

    result = await orch._run_react_tool_call(
        LLMToolCall(
            id="call-1",
            name="search_amenities",
            arguments=json.dumps({"query": "ở đâu"}),
        ),
        user_message="Vinpearl Phú Quốc ở đâu?",
    )

    web_search.search.assert_awaited_once_with("Vinpearl Phú Quốc ở đâu?")
    assert result["fallback"] == "tavily"
    assert result["results"] == [
        {
            "text": "Vinpearl Phú Quốc nằm tại Bãi Dài, Gành Dầu, Phú Quốc.",
            "meta": {
                "source": "https://vinpearl.com/vi/hotels-phu-quoc",
                "retrieval": "tavily",
            },
            "score": 0.0,
        }
    ]


@pytest.mark.asyncio
async def test_search_amenities_irrelevant_shuttle_result_falls_back_to_tavily():
    registry = ToolRegistry()

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        return {
            "ok": True,
            "query": query,
            "results": [
                {
                    "text": "Vinpearl Phú Quốc has beach villas and pools.",
                    "meta": {"source": "overview"},
                    "score": 0.8,
                }
            ],
        }

    web_search = AsyncMock()
    web_search.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Có xe shuttle/xe bus miễn phí từ sân bay cho khách đặt phòng Vinpearl.",
                "source": "https://vinpearl.com/vi/hotels-phu-quoc",
            }
        ],
    }
    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
        web_search=web_search,
    )

    result = await orch._run_react_tool_call(
        LLMToolCall(
            id="call-1",
            name="search_amenities",
            arguments=json.dumps({"query": "xe đưa đón sân bay"}),
        ),
        user_message="Vinpearl có xe đưa đón sân bay không?",
    )

    web_search.search.assert_awaited_once_with(
        "Vinpearl có xe đưa đón sân bay không?"
    )
    assert result["fallback"] == "tavily"
    assert "shuttle" in result["results"][0]["text"]


@pytest.mark.asyncio
async def test_search_amenities_irrelevant_cancellation_result_falls_back_to_tavily():
    registry = ToolRegistry()

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        return {
            "ok": True,
            "query": query,
            "results": [
                {
                    "text": "Vinpearl has restaurants and pools.",
                    "meta": {"source": "overview"},
                    "score": 0.8,
                }
            ],
        }

    web_search = AsyncMock()
    web_search.search.return_value = {
        "ok": True,
        "results": [
            {
                "text": "Chính sách hoàn hủy Vinpearl phụ thuộc vào từng gói đặt phòng.",
                "source": "https://vinpearl.com/vi",
            }
        ],
    }
    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
        web_search=web_search,
    )

    result = await orch._run_react_tool_call(
        LLMToolCall(
            id="call-1",
            name="search_amenities",
            arguments=json.dumps({"query": "chính sách hủy phòng"}),
        ),
        user_message="Chính sách hủy phòng Vinpearl thế nào?",
    )

    web_search.search.assert_awaited_once_with(
        "Chính sách hủy phòng Vinpearl thế nào?"
    )
    assert result["fallback"] == "tavily"
    assert "hoàn hủy" in result["results"][0]["text"]


@pytest.mark.asyncio
async def test_web_tool_for_stable_vinpearl_query_tries_vector_first():
    registry = ToolRegistry()
    local_queries: list[str] = []
    web_queries: list[str] = []

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        local_queries.append(query)
        return {
            "ok": True,
            "query": query,
            "results": [
                {
                    "text": "Vinpearl Phú Quốc is at Bãi Dài.",
                    "meta": {"source": "knowledge"},
                    "score": 0.9,
                }
            ],
        }

    @registry.register("search_vinpearl_web", "Search official Vinpearl web")
    async def search_vinpearl_web(query: str, request_id: str):
        web_queries.append(query)
        return {"ok": True, "results": [{"text": "web", "source": "web"}]}

    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
    )

    result = await orch._run_react_tool_call(
        LLMToolCall(
            id="call-web",
            name="search_vinpearl_web",
            arguments=json.dumps({"query": "Vinpearl Phu Quoc"}),
        ),
        user_message="Vinpearl Phu Quoc",
    )

    assert local_queries == ["Vinpearl Phu Quoc"]
    assert web_queries == []
    assert result["web_skipped"] == "vector_first"
    assert result["results"][0]["text"] == "Vinpearl Phú Quốc is at Bãi Dài."


@pytest.mark.asyncio
async def test_web_tool_for_live_vinpearl_query_does_not_try_vector_first():
    registry = ToolRegistry()
    local_queries: list[str] = []
    web_queries: list[str] = []

    @registry.register("search_amenities", "Search resort knowledge")
    async def search_amenities(query: str, request_id: str):
        local_queries.append(query)
        return {"ok": True, "results": [{"text": "local", "source": "knowledge"}]}

    @registry.register("search_vinpearl_web", "Search official Vinpearl web")
    async def search_vinpearl_web(query: str, request_id: str):
        web_queries.append(query)
        return {
            "ok": True,
            "results": [
                {
                    "text": "Hotline Vinpearl Phú Quốc is available online.",
                    "source": "https://vinpearl.com/vi/hotels-phu-quoc",
                }
            ],
        }

    orch = ConciergeOrchestrator(
        llm_provider=FakeReActProvider(),
        rag=None,
        tool_registry=registry,
        memory_store=_memory(),
    )

    result = await orch._run_react_tool_call(
        LLMToolCall(
            id="call-web",
            name="search_vinpearl_web",
            arguments=json.dumps({"query": "Số điện thoại Vinpearl Phú Quốc?"}),
        ),
        user_message="Số điện thoại Vinpearl Phú Quốc?",
    )

    assert local_queries == []
    assert web_queries == ["Số điện thoại Vinpearl Phú Quốc?"]
    assert result["results"][0]["source"] == "https://vinpearl.com/vi/hotels-phu-quoc"
