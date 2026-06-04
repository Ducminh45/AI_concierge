"""Per-call LLM tracing — captures tokens, latency, and estimated cost."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .llm_providers import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger("monster_resort")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LLMCallTrace:
    """Single LLM call trace record."""

    provider_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    timestamp: str  # ISO-8601
    session_id: Optional[str] = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Cost calculator
# ---------------------------------------------------------------------------

# Prices are per 1 million tokens: (input_price, output_price)
_DEFAULT_PRICING: Dict[Tuple[str, str], Tuple[float, float]] = {
    # OpenAI
    ("openai", "gpt-4o-mini"): (0.15, 0.60),
    ("openai", "gpt-4o-mini-2024-07-18"): (0.15, 0.60),
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4o-2024-08-06"): (2.50, 10.00),
    # Anthropic
    ("anthropic", "claude-sonnet-4-20250514"): (3.00, 15.00),
    ("anthropic", "claude-3-5-sonnet-20241022"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-20250414"): (0.80, 4.00),
    ("anthropic", "claude-3-5-haiku-20241022"): (0.80, 4.00),
    # Ollama (local) -- no cost
    ("ollama", "*"): (0.0, 0.0),
}


class CostCalculator:
    """Maps (provider, model) to per-token pricing."""

    def __init__(
        self, pricing: Optional[Dict[Tuple[str, str], Tuple[float, float]]] = None
    ):
        self._pricing = dict(_DEFAULT_PRICING)
        if pricing:
            self._pricing.update(pricing)

    def estimate(
        self, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Return estimated cost in USD for the given token counts."""
        key = (provider, model)
        if key not in self._pricing:
            # Try wildcard match for the provider
            key = (provider, "*")
        prices = self._pricing.get(key)
        if prices is None:
            return 0.0

        input_price, output_price = prices
        cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
        return round(cost, 8)


# ---------------------------------------------------------------------------
# Tracer — wraps any LLMProvider (including ModelRouter)
# ---------------------------------------------------------------------------

class LLMTracer(LLMProvider):
    """Transparent tracing wrapper for any LLMProvider."""

    def __init__(
        self,
        provider: LLMProvider,
        max_traces: int = 100,
        cost_calculator: Optional[CostCalculator] = None,
    ):
        self._provider = provider
        self._traces: deque[LLMCallTrace] = deque(maxlen=max_traces)
        self._cost = cost_calculator or CostCalculator()

    # -- LLMProvider interface ------------------------------------------------

    @property
    def name(self) -> str:
        return self._provider.name

    def translate_tool_schemas(self, openai_schemas: List[dict]) -> List[dict]:
        return self._provider.translate_tool_schemas(openai_schemas)

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[dict]] = None,
        model: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> LLMResponse:
        start = time.perf_counter()
        response = await self._provider.chat(
            messages, tools, model, response_format=response_format,
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        prompt_tokens = response.usage.get("prompt_tokens", 0)
        completion_tokens = response.usage.get("completion_tokens", 0)

        cost = self._cost.estimate(
            response.provider, response.model, prompt_tokens, completion_tokens
        )

        trace = LLMCallTrace(
            provider_name=response.provider,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=elapsed_ms,
            estimated_cost_usd=cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._traces.append(trace)

        # Structured JSON log line
        logger.info(
            "llm_call_traced",
            extra={
                "trace": trace.to_dict(),
            },
        )

        return response

    # -- Query interface ------------------------------------------------------

    def recent_traces(self, limit: int = 100) -> List[dict]:
        """Return recent traces as dicts, newest first."""
        traces = list(self._traces)
        traces.reverse()
        return [t.to_dict() for t in traces[:limit]]

    def summary(self) -> dict:
        """Aggregate stats across stored traces."""
        traces = list(self._traces)
        if not traces:
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_estimated_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
            }

        total_prompt = sum(t.prompt_tokens for t in traces)
        total_completion = sum(t.completion_tokens for t in traces)
        total_cost = sum(t.estimated_cost_usd for t in traces)
        avg_latency = sum(t.latency_ms for t in traces) / len(traces)

        return {
            "total_calls": len(traces),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_estimated_cost_usd": round(total_cost, 6),
            "avg_latency_ms": round(avg_latency, 2),
        }

    # -- Expose wrapped provider for duck-typing compatibility ----------------

    @property
    def providers(self):
        """Forward .providers so ModelRouter attributes stay reachable."""
        return getattr(self._provider, "providers", [])

    @property
    def fallback_enabled(self):
        return getattr(self._provider, "fallback_enabled", True)
