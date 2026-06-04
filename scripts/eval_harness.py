#!/usr/bin/env python3
"""Evaluation harness that runs test cases through the RAG pipeline and produces a quality scorecard."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure project root is importable when running as a script
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    """A single evaluation test case loaded from the JSON file."""

    id: int
    query: str
    expected_tool: Optional[str]
    expected_keywords: List[str]
    category: str


@dataclass
class EvalResult:
    """Result of running one test case."""

    case_id: int
    query: str
    category: str
    passed: bool
    # Individual scores
    retrieval_relevance: float
    tool_correct: bool
    response_keyword_hit: float
    hallucination_score: float
    hallucination_level: str
    latency_s: float
    # Details for failed-case reporting
    expected_tool: Optional[str]
    actual_tool: Optional[str]
    response_snippet: str
    failure_reasons: List[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Aggregated evaluation report."""

    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    category_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    avg_hallucination_score: float = 0.0
    avg_retrieval_relevance: float = 0.0
    tool_selection_accuracy: float = 0.0
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    results: List[EvalResult] = field(default_factory=list)
    failed_cases: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline interface
# ---------------------------------------------------------------------------


class PipelineRunner:
    """Abstract interface that the harness calls for each test query."""

    async def run(self, query: str) -> Dict[str, Any]:
        """Execute a query and return a dict with keys:

        - ``response``   (str)  – the assistant's final answer
        - ``tool_called`` (str | None)  – name of tool invoked, if any
        - ``contexts``   (list[str])  – RAG chunks retrieved
        """
        raise NotImplementedError


class MockPipelineRunner(PipelineRunner):
    """Deterministic stub used to exercise the harness without live models."""

    TOOL_KEYWORDS = {
        "book": "book_room",
        "reserve": "book_room",
        "booking": "get_booking",
        "look up booking": "get_booking",
        "cancel": "cancel_booking",
        "amenities": "search_amenities",
        "search": "search_amenities",
        "pool": "search_amenities",
        "restaurant": "search_amenities",
        "wifi": "search_amenities",
        "wi-fi": "search_amenities",
        "pet": "search_amenities",
        "room service": "search_amenities",
        "check-in": "search_amenities",
        "checkout": "search_amenities",
        "directions": "search_amenities",
        "scariest": "search_amenities",
        "werewolf": "search_amenities",
        "frankenstein": "search_amenities",
    }

    async def run(self, query: str) -> Dict[str, Any]:
        lower = query.lower()
        tool_called = None
        for kw, tool_name in self.TOOL_KEYWORDS.items():
            if kw in lower:
                tool_called = tool_name
                break

        # Produce a synthetic response that echoes expected keywords
        response = (
            f"Welcome to the Monster Resort! Regarding your query about "
            f"'{query}': We have a pool, spa, restaurant, and coffin beds. "
            f"Checkout time is 11am. Booking confirmed. WiFi available. "
            f"Pets welcome per our pet policy. Room service runs until 2am. "
            f"Check-in hours are 3pm-midnight. We're glad to help!"
        )
        contexts = [
            "The Monster Resort features a heated pool, full-service spa, "
            "and three themed restaurants.",
            "Checkout time is 11:00 AM. Check-in begins at 3:00 PM.",
            "Complimentary WiFi is provided in all rooms and common areas.",
            "Pets are welcome with prior approval. See our pet policy.",
            "Room service is available 24 hours. After midnight menu is limited.",
        ]
        return {
            "response": response,
            "tool_called": tool_called,
            "contexts": contexts,
        }


class LivePipelineRunner(PipelineRunner):
    """Runs queries through the real concierge pipeline.

    Requires the application to be importable and API keys to be set.
    """

    def __init__(self):
        self._initialized = False

    async def _ensure_init(self):
        if self._initialized:
            return
        # Lazy imports so the harness can load even if deps are missing
        from app.core.llm_providers import (
            LLMMessage,
            ModelRouter,
            OpenAIProvider,
        )
        from app.core.tools import VALID_HOTELS

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set — cannot run in live mode. "
                "Use --mock or export the key."
            )

        self._router = ModelRouter([OpenAIProvider(api_key=api_key)])
        self._LLMMessage = LLMMessage
        self._initialized = True

    async def run(self, query: str) -> Dict[str, Any]:
        await self._ensure_init()

        messages = [
            self._LLMMessage(
                role="system",
                content=(
                    "You are the Monster Resort Concierge. Answer the guest's "
                    "question helpfully. If a tool is appropriate, call it."
                ),
            ),
            self._LLMMessage(role="user", content=query),
        ]

        resp = await self._router.chat(messages)

        tool_called = None
        if resp.tool_calls:
            tool_called = resp.tool_calls[0].name

        return {
            "response": resp.content,
            "tool_called": tool_called,
            "contexts": [],  # live mode doesn't have easy access to RAG chunks
        }


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------


def _keyword_hit_rate(text: str, keywords: List[str]) -> float:
    """Fraction of expected keywords found (case-insensitive) in *text*."""
    if not keywords:
        return 1.0
    lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in lower)
    return hits / len(keywords)


def _retrieval_relevance(contexts: List[str], keywords: List[str]) -> float:
    """Fraction of expected keywords found across all retrieved contexts."""
    if not keywords:
        return 1.0
    if not contexts:
        return 0.0
    combined = " ".join(contexts).lower()
    hits = sum(1 for kw in keywords if kw.lower() in combined)
    return hits / len(keywords)


def _compute_hallucination_score(
    response: str, contexts: List[str], query: str
) -> tuple[float, str]:
    """Run the HallucinationDetector and return (score, level).

    Falls back to a simple token-overlap heuristic if the detector's
    dependencies (sentence-transformers) are unavailable.
    """
    try:
        from app.validation.hallucination import HallucinationDetector

        detector = HallucinationDetector()
        result = detector.score_response(response, contexts)
        return result.overall_score, result.level.value
    except Exception:
        # Fallback: simple token overlap
        if not contexts:
            return 0.0, "LOW"
        import re

        resp_tokens = set(re.findall(r"\w+", response.lower()))
        ctx_tokens: set[str] = set()
        for ctx in contexts:
            ctx_tokens.update(re.findall(r"\w+", ctx.lower()))
        if not resp_tokens:
            return 0.0, "LOW"
        overlap = len(resp_tokens & ctx_tokens) / len(resp_tokens)
        if overlap >= 0.7:
            level = "HIGH"
        elif overlap >= 0.4:
            level = "MEDIUM"
        else:
            level = "LOW"
        return overlap, level


async def evaluate_case(
    case: EvalCase,
    runner: PipelineRunner,
) -> EvalResult:
    """Run a single evaluation case and return the result."""

    start = time.perf_counter()
    try:
        output = await runner.run(case.query)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return EvalResult(
            case_id=case.id,
            query=case.query,
            category=case.category,
            passed=False,
            retrieval_relevance=0.0,
            tool_correct=False,
            response_keyword_hit=0.0,
            hallucination_score=0.0,
            hallucination_level="LOW",
            latency_s=elapsed,
            expected_tool=case.expected_tool,
            actual_tool=None,
            response_snippet="",
            failure_reasons=[f"Pipeline error: {exc}"],
        )
    elapsed = time.perf_counter() - start

    response = output.get("response", "")
    tool_called = output.get("tool_called")
    contexts = output.get("contexts", [])

    # -- Metrics --
    retrieval_rel = _retrieval_relevance(contexts, case.expected_keywords)
    keyword_hit = _keyword_hit_rate(response, case.expected_keywords)
    tool_correct = case.expected_tool == tool_called
    hall_score, hall_level = _compute_hallucination_score(
        response, contexts, case.query
    )

    # -- Pass / fail logic --
    failure_reasons: list[str] = []

    if not tool_correct:
        failure_reasons.append(
            f"Expected tool '{case.expected_tool}', got '{tool_called}'"
        )
    if keyword_hit < 0.5:
        failure_reasons.append(
            f"Response keyword hit rate too low: {keyword_hit:.0%}"
        )
    if retrieval_rel < 0.3 and contexts:
        failure_reasons.append(
            f"Retrieval relevance too low: {retrieval_rel:.0%}"
        )

    passed = len(failure_reasons) == 0

    return EvalResult(
        case_id=case.id,
        query=case.query,
        category=case.category,
        passed=passed,
        retrieval_relevance=retrieval_rel,
        tool_correct=tool_correct,
        response_keyword_hit=keyword_hit,
        hallucination_score=hall_score,
        hallucination_level=hall_level,
        latency_s=round(elapsed, 4),
        expected_tool=case.expected_tool,
        actual_tool=tool_called,
        response_snippet=response[:200],
        failure_reasons=failure_reasons,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_report(results: List[EvalResult]) -> EvalReport:
    """Aggregate individual results into a scorecard."""

    total = len(results)
    passed = sum(1 for r in results if r.passed)

    # -- Per-category breakdown --
    categories: Dict[str, Dict[str, Any]] = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r.passed:
            categories[cat]["passed"] += 1
    for info in categories.values():
        info["pass_rate"] = (
            round(info["passed"] / info["total"], 4) if info["total"] else 0.0
        )

    # -- Aggregate metrics --
    hall_scores = [r.hallucination_score for r in results]
    ret_scores = [r.retrieval_relevance for r in results]
    latencies = sorted(r.latency_s for r in results)

    tool_cases = [r for r in results if r.expected_tool is not None]
    tool_accuracy = (
        sum(1 for r in tool_cases if r.tool_correct) / len(tool_cases)
        if tool_cases
        else 1.0
    )

    def percentile(data: List[float], pct: float) -> float:
        if not data:
            return 0.0
        k = (len(data) - 1) * (pct / 100)
        f = int(k)
        c = f + 1
        if c >= len(data):
            return data[-1]
        return data[f] + (k - f) * (data[c] - data[f])

    # -- Failed-case summaries --
    failed_cases = []
    for r in results:
        if not r.passed:
            failed_cases.append(
                {
                    "case_id": r.case_id,
                    "query": r.query,
                    "reasons": r.failure_reasons,
                }
            )

    return EvalReport(
        total=total,
        passed=passed,
        pass_rate=round(passed / total, 4) if total else 0.0,
        category_results=categories,
        avg_hallucination_score=round(statistics.mean(hall_scores), 4)
        if hall_scores
        else 0.0,
        avg_retrieval_relevance=round(statistics.mean(ret_scores), 4)
        if ret_scores
        else 0.0,
        tool_selection_accuracy=round(tool_accuracy, 4),
        latency_p50=round(percentile(latencies, 50), 4),
        latency_p95=round(percentile(latencies, 95), 4),
        results=results,
        failed_cases=failed_cases,
    )


def print_report(report: EvalReport) -> None:
    """Pretty-print the evaluation scorecard to stdout."""

    pct = lambda v: f"{v * 100:.0f}%"

    print("\n=== RAG Evaluation Report ===")
    print(f"Test Cases: {report.total}")
    print(f"Pass Rate: {pct(report.pass_rate)} ({report.passed}/{report.total})")

    print("\nBy Category:")
    for cat, info in sorted(report.category_results.items()):
        print(
            f"  {cat}: {pct(info['pass_rate'])} "
            f"({info['passed']}/{info['total']})"
        )

    print("\nMetrics:")
    print(f"  Avg Hallucination Score: {report.avg_hallucination_score:.2f}")
    print(f"  Avg Retrieval Relevance: {report.avg_retrieval_relevance:.2f}")
    print(f"  Tool Selection Accuracy: {pct(report.tool_selection_accuracy)}")
    print(f"  Latency p50: {report.latency_p50:.3f}s | p95: {report.latency_p95:.3f}s")

    if report.failed_cases:
        print("\nFailed Cases:")
        for fc in report.failed_cases:
            reasons = "; ".join(fc["reasons"])
            print(f"  [{fc['case_id']}] \"{fc['query']}\" - {reasons}")

    print()


def save_report(report: EvalReport, output_path: Path) -> None:
    """Persist the report as JSON for historical tracking."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert dataclass tree to plain dicts
    data = {
        "total": report.total,
        "passed": report.passed,
        "pass_rate": report.pass_rate,
        "category_results": report.category_results,
        "avg_hallucination_score": report.avg_hallucination_score,
        "avg_retrieval_relevance": report.avg_retrieval_relevance,
        "tool_selection_accuracy": report.tool_selection_accuracy,
        "latency_p50": report.latency_p50,
        "latency_p95": report.latency_p95,
        "failed_cases": report.failed_cases,
        "results": [asdict(r) for r in report.results],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logging.getLogger(__name__).info("Report saved to %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_harness(
    test_file: Path,
    output_path: Path,
    runner: PipelineRunner,
) -> EvalReport:
    """Load test cases, evaluate each one, build and save the report."""

    logger = logging.getLogger(__name__)

    with open(test_file) as f:
        raw_cases = json.load(f)

    cases = [EvalCase(**c) for c in raw_cases]
    logger.info("Loaded %d test cases from %s", len(cases), test_file)

    results: List[EvalResult] = []
    for case in cases:
        logger.info("Running case %d: %s", case.id, case.query[:60])
        result = await evaluate_case(case, runner)
        status = "PASS" if result.passed else "FAIL"
        logger.info("  -> %s (%.3fs)", status, result.latency_s)
        results.append(result)

    report = build_report(results)
    print_report(report)
    save_report(report, output_path)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monster Resort RAG Evaluation Harness"
    )
    parser.add_argument(
        "--test-file",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval_cases.json",
        help="Path to JSON file with evaluation test cases",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "eval_report.json",
        help="Path to write the JSON report",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Run against the live LLM pipeline (requires API keys)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    runner: PipelineRunner
    if args.live:
        runner = LivePipelineRunner()
    else:
        runner = MockPipelineRunner()

    asyncio.run(run_harness(args.test_file, args.output, runner))


if __name__ == "__main__":
    main()
