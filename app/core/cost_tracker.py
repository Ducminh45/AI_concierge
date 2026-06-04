"""Cost Tracker — estimates per-request cost from model name and token counts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

import yaml

logger = logging.getLogger(__name__)

PRICING_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "model_pricing.yaml"


@lru_cache(maxsize=1)
def _load_pricing() -> Dict[str, Tuple[float, float]]:
    """Return model pricing dict from YAML config, cached after first call."""
    try:
        with open(PRICING_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        pricing = {}
        for model, rates in raw.items():
            if isinstance(rates, dict):
                pricing[model] = (
                    float(rates.get("input", 0.0)),
                    float(rates.get("output", 0.0)),
                )
        logger.info("pricing_loaded", extra={"models": len(pricing)})
        return pricing
    except FileNotFoundError:
        logger.warning("pricing_file_not_found", extra={"path": PRICING_PATH})
        return _fallback_pricing()
    except Exception as exc:
        logger.error("pricing_load_failed", extra={"error": str(exc)})
        return _fallback_pricing()


def _fallback_pricing() -> Dict[str, Tuple[float, float]]:
    """Return hardcoded fallback pricing."""
    return {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "llama3": (0.0, 0.0),
    }


def reload_pricing() -> None:
    """Clear the pricing cache so the next call re-reads from disk."""
    _load_pricing.cache_clear()
    logger.info("pricing_cache_cleared")


def estimate_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """Return estimated cost in USD for a single LLM call."""
    model_pricing = _load_pricing()
    pricing = model_pricing.get(model)

    if pricing is None:
        for key in sorted(model_pricing, key=len, reverse=True):
            if model.startswith(key):
                pricing = model_pricing[key]
                break

    if pricing is None:
        logger.warning("cost_tracker_unknown_model", extra={"model": model})
        pricing = model_pricing.get("gpt-4o-mini", (0.15, 0.60))

    input_cost = (prompt_tokens / 1_000_000) * pricing[0]
    output_cost = (completion_tokens / 1_000_000) * pricing[1]
    return round(input_cost + output_cost, 6)


@dataclass
class CostAccumulator:
    """Accumulates cost across multiple LLM calls."""

    total_cost_usd: float = 0.0
    call_count: int = 0
    _by_model: dict[str, float] = field(default_factory=dict)

    def record(self, model: str, usage: dict) -> float:
        """Record a single call's cost and return it."""
        cost = estimate_cost(
            model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        self.total_cost_usd = round(self.total_cost_usd + cost, 6)
        self.call_count += 1
        self._by_model[model] = round(self._by_model.get(model, 0.0) + cost, 6)
        return cost

    def summary(self) -> dict:
        return {
            "total_cost_usd": self.total_cost_usd,
            "call_count": self.call_count,
            "by_model": dict(self._by_model),
        }
