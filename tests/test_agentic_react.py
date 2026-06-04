from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core.llm_providers import LLMMessage, LLMResponse, LLMToolCall
from app.core.orchestrator import ConciergeOrchestrator, IntentType, Plan
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
