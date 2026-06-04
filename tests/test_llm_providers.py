"""Tests for the multi-model LLM orchestration layer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.llm_providers import (
    LLMMessage,
    LLMToolCall,
    LLMResponse,
    AnthropicProvider,
    ModelRouter,
)


# ---------------------------------------------------------------------------
# Data class construction tests
# ---------------------------------------------------------------------------


class TestLLMMessage:
    def test_basic_construction(self):
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls == []
        assert msg.tool_call_id is None

    def test_with_tool_calls(self):
        tc = LLMToolCall(
            id="tc_1", name="book_room",
            arguments='{"guest": "Drac"}'
        )
        msg = LLMMessage(role="assistant", content="", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "book_room"

    def test_tool_message(self):
        msg = LLMMessage(
            role="tool", content='{"ok": true}',
            tool_call_id="tc_1"
        )
        assert msg.tool_call_id == "tc_1"


class TestLLMResponse:
    def test_basic_construction(self):
        resp = LLMResponse(
            content="Hello darkness", model="gpt-4o",
            provider="openai"
        )
        assert resp.content == "Hello darkness"
        assert resp.provider == "openai"
        assert resp.tool_calls == []
        assert resp.usage == {}


# ---------------------------------------------------------------------------
# Anthropic schema translation
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    def test_translate_tool_schemas(self):
        openai_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "book_room",
                    "description": "Book a room",
                    "parameters": {
                        "type": "object",
                        "properties": {"guest_name": {"type": "string"}},
                        "required": ["guest_name"],
                    },
                },
            }
        ]
        provider = AnthropicProvider.__new__(AnthropicProvider)
        result = provider.translate_tool_schemas(openai_schemas)

        assert len(result) == 1
        assert result[0]["name"] == "book_room"
        assert result[0]["description"] == "Book a room"
        assert "input_schema" in result[0]
        guest_type = (
            result[0]["input_schema"]["properties"]["guest_name"]["type"]
        )
        assert guest_type == "string"


# ---------------------------------------------------------------------------
# ModelRouter fallback tests
# ---------------------------------------------------------------------------


class TestModelRouter:
    @pytest.mark.asyncio
    async def test_first_provider_succeeds(self):
        p1 = MagicMock()
        p1.name = "mock1"
        p1.chat = AsyncMock(
            return_value=LLMResponse(content="ok", provider="mock1")
        )
        router = ModelRouter(providers=[p1])
        resp = await router.chat([LLMMessage(role="user", content="hi")])
        assert resp.content == "ok"
        assert resp.provider == "mock1"

    @pytest.mark.asyncio
    async def test_fallback_to_second_provider(self):
        p1 = MagicMock()
        p1.name = "failing"
        p1.chat = AsyncMock(side_effect=RuntimeError("down"))

        p2 = MagicMock()
        p2.name = "backup"
        p2.chat = AsyncMock(
            return_value=LLMResponse(content="from backup", provider="backup")
        )

        router = ModelRouter(providers=[p1, p2], fallback_enabled=True)
        resp = await router.chat([LLMMessage(role="user", content="hi")])
        assert resp.content == "from backup"
        assert resp.provider == "backup"

    @pytest.mark.asyncio
    async def test_no_fallback_raises(self):
        p1 = MagicMock()
        p1.name = "failing"
        p1.chat = AsyncMock(side_effect=RuntimeError("down"))

        router = ModelRouter(providers=[p1], fallback_enabled=False)
        with pytest.raises(RuntimeError, match="down"):
            await router.chat([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        p1 = MagicMock()
        p1.name = "fail1"
        p1.chat = AsyncMock(side_effect=RuntimeError("err1"))

        p2 = MagicMock()
        p2.name = "fail2"
        p2.chat = AsyncMock(side_effect=RuntimeError("err2"))

        router = ModelRouter(providers=[p1, p2], fallback_enabled=True)
        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await router.chat([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_provider_priority_order(self):
        """First provider in list is tried first."""
        call_order = []

        p1 = MagicMock()
        p1.name = "first"

        async def p1_chat(*a, **k):
            call_order.append("first")
            return LLMResponse(content="first", provider="first")

        p1.chat = p1_chat

        p2 = MagicMock()
        p2.name = "second"

        async def p2_chat(*a, **k):
            call_order.append("second")
            return LLMResponse(content="second", provider="second")

        p2.chat = p2_chat

        router = ModelRouter(providers=[p1, p2])
        resp = await router.chat([LLMMessage(role="user", content="hi")])
        assert call_order == ["first"]
        assert resp.provider == "first"
