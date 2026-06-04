"""
Tests for LLM observability: CostCalculator, LLMCallTrace, and LLMTracer.
"""

import pytest

from app.core.llm_providers import LLMMessage, LLMProvider, LLMResponse
from app.core.observability import CostCalculator, LLMCallTrace, LLMTracer


# ---------------------------------------------------------------------------
# Fake provider for testing
# ---------------------------------------------------------------------------


class FakeProvider(LLMProvider):
    """Deterministic provider that returns canned responses."""

    def __init__(self, response: LLMResponse | None = None):
        self._response = response or LLMResponse(
            content="Hello from fake",
            model="gpt-4o-mini",
            provider="openai",
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        )

    @property
    def name(self) -> str:
        return "fake"

    def translate_tool_schemas(self, openai_schemas):
        return openai_schemas

    async def chat(self, messages, tools=None, model=None, **kwargs):
        return self._response


# ---------------------------------------------------------------------------
# CostCalculator
# ---------------------------------------------------------------------------


class TestCostCalculator:
    def test_known_model_returns_nonzero(self):
        calc = CostCalculator()
        cost = calc.estimate("openai", "gpt-4o-mini", 1000, 500)
        # input: 1000 * 0.15 / 1M = 0.00015, output: 500 * 0.60 / 1M = 0.0003
        assert cost == pytest.approx(0.00015 + 0.0003, abs=1e-8)

    def test_unknown_model_returns_zero(self):
        calc = CostCalculator()
        cost = calc.estimate("unknown_provider", "mystery-model", 1000, 500)
        assert cost == 0.0

    def test_ollama_wildcard_returns_zero(self):
        calc = CostCalculator()
        cost = calc.estimate("ollama", "llama3", 5000, 2000)
        assert cost == 0.0

    def test_anthropic_sonnet_pricing(self):
        calc = CostCalculator()
        cost = calc.estimate("anthropic", "claude-sonnet-4-20250514", 1_000_000, 0)
        assert cost == pytest.approx(3.0, abs=1e-6)

    def test_custom_pricing_override(self):
        custom = {("custom", "my-model"): (1.0, 2.0)}
        calc = CostCalculator(pricing=custom)
        cost = calc.estimate("custom", "my-model", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.0, abs=1e-6)


# ---------------------------------------------------------------------------
# LLMCallTrace
# ---------------------------------------------------------------------------


class TestLLMCallTrace:
    def test_to_dict_contains_all_fields(self):
        trace = LLMCallTrace(
            provider_name="openai",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=123.45,
            estimated_cost_usd=0.001,
            timestamp="2025-01-01T00:00:00+00:00",
        )
        d = trace.to_dict()
        assert d["provider_name"] == "openai"
        assert d["model"] == "gpt-4o-mini"
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 50
        assert d["latency_ms"] == 123.45
        assert d["estimated_cost_usd"] == 0.001
        assert "trace_id" in d

    def test_trace_id_auto_generated(self):
        t1 = LLMCallTrace(
            provider_name="x", model="m", prompt_tokens=0,
            completion_tokens=0, latency_ms=0, estimated_cost_usd=0,
            timestamp="",
        )
        t2 = LLMCallTrace(
            provider_name="x", model="m", prompt_tokens=0,
            completion_tokens=0, latency_ms=0, estimated_cost_usd=0,
            timestamp="",
        )
        assert t1.trace_id != t2.trace_id


# ---------------------------------------------------------------------------
# LLMTracer
# ---------------------------------------------------------------------------


class TestLLMTracer:
    @pytest.mark.asyncio
    async def test_chat_returns_original_response(self):
        provider = FakeProvider()
        tracer = LLMTracer(provider)
        messages = [LLMMessage(role="user", content="hi")]

        response = await tracer.chat(messages)

        assert response.content == "Hello from fake"
        assert response.provider == "openai"

    @pytest.mark.asyncio
    async def test_chat_records_trace(self):
        provider = FakeProvider()
        tracer = LLMTracer(provider)
        messages = [LLMMessage(role="user", content="hi")]

        await tracer.chat(messages)

        traces = tracer.recent_traces()
        assert len(traces) == 1
        trace = traces[0]
        assert trace["provider_name"] == "openai"
        assert trace["model"] == "gpt-4o-mini"
        assert trace["prompt_tokens"] == 50
        assert trace["completion_tokens"] == 20
        assert trace["latency_ms"] >= 0  # fake provider returns instantly
        assert trace["estimated_cost_usd"] > 0
        assert trace["timestamp"] != ""

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate(self):
        provider = FakeProvider()
        tracer = LLMTracer(provider)
        messages = [LLMMessage(role="user", content="hi")]

        for _ in range(5):
            await tracer.chat(messages)

        traces = tracer.recent_traces()
        assert len(traces) == 5

    @pytest.mark.asyncio
    async def test_max_traces_bounded(self):
        provider = FakeProvider()
        tracer = LLMTracer(provider, max_traces=3)
        messages = [LLMMessage(role="user", content="hi")]

        for _ in range(10):
            await tracer.chat(messages)

        traces = tracer.recent_traces()
        assert len(traces) == 3

    @pytest.mark.asyncio
    async def test_summary_aggregation(self):
        provider = FakeProvider()
        tracer = LLMTracer(provider)
        messages = [LLMMessage(role="user", content="hi")]

        await tracer.chat(messages)
        await tracer.chat(messages)

        summary = tracer.summary()
        assert summary["total_calls"] == 2
        assert summary["total_prompt_tokens"] == 100
        assert summary["total_completion_tokens"] == 40
        assert summary["total_estimated_cost_usd"] > 0
        assert summary["avg_latency_ms"] >= 0  # fake provider returns instantly

    @pytest.mark.asyncio
    async def test_summary_empty(self):
        tracer = LLMTracer(FakeProvider())
        summary = tracer.summary()
        assert summary["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_recent_traces_newest_first(self):
        resp1 = LLMResponse(
            content="a", model="m1", provider="openai",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        resp2 = LLMResponse(
            content="b", model="m2", provider="openai",
            usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        )

        class ToggleProvider(LLMProvider):
            def __init__(self):
                self._call_count = 0

            @property
            def name(self):
                return "toggle"

            def translate_tool_schemas(self, s):
                return s

            async def chat(self, messages, tools=None, model=None, **kwargs):
                self._call_count += 1
                return resp1 if self._call_count == 1 else resp2

        tracer = LLMTracer(ToggleProvider())
        messages = [LLMMessage(role="user", content="hi")]
        await tracer.chat(messages)
        await tracer.chat(messages)

        traces = tracer.recent_traces()
        assert traces[0]["model"] == "m2"
        assert traces[1]["model"] == "m1"

    def test_name_delegates_to_provider(self):
        tracer = LLMTracer(FakeProvider())
        assert tracer.name == "fake"

    def test_translate_tool_schemas_delegates(self):
        tracer = LLMTracer(FakeProvider())
        schemas = [{"type": "function", "function": {"name": "test"}}]
        assert tracer.translate_tool_schemas(schemas) == schemas
