"""
Tests for native structured output support.

Verifies the fallback chain:
    1. Native API structured output (direct json.loads)
    2. StructuredOutputParser._extract_json (raw_decode extraction)
    3. Keyword heuristic
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.llm_providers import (
    LLMProvider,
    LLMResponse,
    OllamaProvider,
    OpenAIProvider,
)
from app.core.orchestrator import ConciergeOrchestrator, IntentType


# ---------------------------------------------------------------------------
# Provider supports_response_format property
# ---------------------------------------------------------------------------


class TestSupportsResponseFormat:
    """Verify supports_response_format is correctly reported per provider."""

    def test_base_provider_defaults_false(self):
        assert LLMProvider.supports_response_format.fget(None) is False

    def test_openai_supports_response_format(self):
        # Access from the class to avoid __init__ side effects
        assert OpenAIProvider.supports_response_format.fget(None) is True

    def test_ollama_does_not_support_response_format(self):
        assert OllamaProvider.supports_response_format.fget(None) is False


# ---------------------------------------------------------------------------
# _parse_plan fallback chain
# ---------------------------------------------------------------------------


class TestParsePlanFallbackChain:
    """Verify the three-level fallback: native -> raw_decode -> heuristic."""

    @pytest.fixture()
    def parse(self):
        orch = object.__new__(ConciergeOrchestrator)
        return orch._parse_plan

    def test_clean_json_parsed_directly(self, parse):
        raw = json.dumps({
            "intent": "tool",
            "tool_name": "book_room",
            "tool_args": {"guest": "Frankenstein"},
            "search_query": None,
            "reasoning": "Booking request",
        })
        plan = parse(raw)
        assert plan.intent == IntentType.TOOL
        assert plan.tool_name == "book_room"
        assert plan.tool_args == {"guest": "Frankenstein"}

    def test_json_with_prose_falls_to_extract(self, parse):
        raw = (
            'Here is my analysis:\n'
            '{"intent": "knowledge", "search_query": "pool hours", '
            '"reasoning": "wants pool info"}\n'
            'Let me know if you need more.'
        )
        plan = parse(raw)
        assert plan.intent == IntentType.KNOWLEDGE
        assert plan.search_query == "pool hours"

    def test_markdown_fenced_json_falls_to_extract(self, parse):
        raw = '```json\n{"intent": "clarify", "reasoning": "Need check-in date"}\n```'
        plan = parse(raw)
        assert plan.intent == IntentType.CLARIFY

    def test_no_json_uses_keyword_heuristic_tool(self, parse):
        plan = parse("I think we should book a room for the guest")
        assert plan.intent == IntentType.TOOL

    def test_no_json_uses_keyword_heuristic_knowledge(self, parse):
        plan = parse("The guest is asking about the spa facilities")
        assert plan.intent == IntentType.KNOWLEDGE

    def test_no_json_no_keywords_defaults_chitchat(self, parse):
        plan = parse("Hello there friend")
        assert plan.intent == IntentType.CHITCHAT


# ---------------------------------------------------------------------------
# Orchestrator planner requests response_format when supported
# ---------------------------------------------------------------------------


class TestPlannerRequestsStructuredOutput:
    """Verify the planner passes response_format when the provider supports it."""

    @pytest.fixture()
    def mock_provider_with_format(self):
        """Provider that supports response_format."""
        provider = AsyncMock(spec=LLMProvider)
        provider.name = "openai"
        provider.supports_response_format = True
        provider.chat.return_value = LLMResponse(
            content=json.dumps({
                "intent": "chitchat",
                "tool_name": None,
                "tool_args": {},
                "search_query": None,
                "reasoning": "Just a greeting",
            }),
            model="gpt-4o-mini",
            provider="openai",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        return provider

    @pytest.fixture()
    def mock_provider_without_format(self):
        """Provider that does NOT support response_format."""
        provider = AsyncMock(spec=LLMProvider)
        provider.name = "ollama"
        provider.supports_response_format = False
        provider.chat.return_value = LLMResponse(
            content=json.dumps({
                "intent": "chitchat",
                "tool_name": None,
                "tool_args": {},
                "search_query": None,
                "reasoning": "Just a greeting",
            }),
            model="llama3",
            provider="ollama",
            usage={},
        )
        return provider

    def _make_orchestrator(self, provider):
        memory = Mock()
        memory.get_messages.return_value = []
        tool_registry = Mock()
        tool_registry.list.return_value = []
        orch = ConciergeOrchestrator(
            llm_provider=provider,
            rag=Mock(),
            tool_registry=tool_registry,
            memory_store=memory,
        )
        return orch

    @pytest.mark.asyncio
    async def test_sends_response_format_when_supported(self, mock_provider_with_format):
        orch = self._make_orchestrator(mock_provider_with_format)
        plan = await orch.plan("hello", "session-1")

        mock_provider_with_format.chat.assert_called_once()
        call_kwargs = mock_provider_with_format.chat.call_args
        assert call_kwargs.kwargs.get("response_format") == {"type": "json_object"}
        assert plan.intent == IntentType.CHITCHAT

    @pytest.mark.asyncio
    async def test_no_response_format_when_unsupported(self, mock_provider_without_format):
        orch = self._make_orchestrator(mock_provider_without_format)
        plan = await orch.plan("hello", "session-1")

        mock_provider_without_format.chat.assert_called_once()
        call_kwargs = mock_provider_without_format.chat.call_args
        assert call_kwargs.kwargs.get("response_format") is None
        assert plan.intent == IntentType.CHITCHAT
