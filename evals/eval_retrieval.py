#!/usr/bin/env python3
"""Retrieval quality metrics (MRR, Recall@K, Precision@K) against a ground-truth query set."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GroundTruthCase:
    """A single retrieval evaluation case."""

    id: int
    query: str
    relevant_snippets: List[str]
    source_files: List[str]


@dataclass
class QueryMetrics:
    """Retrieval metrics for one query."""

    query_id: int
    query: str
    reciprocal_rank: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    precision_at_3: float
    precision_at_5: float
    precision_at_10: float
    num_retrieved: int
    num_relevant_found: int
    num_relevant_total: int


@dataclass
class RetrievalReport:
    """Aggregated retrieval quality report."""

    mrr: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    precision_at_10: float = 0.0
    num_queries: int = 0
    per_query: List[QueryMetrics] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Relevance check
# ---------------------------------------------------------------------------


def _is_relevant(retrieved_text: str, relevant_snippets: List[str]) -> bool:
    """Check if a retrieved document contains any of the expected snippets.

    Uses case-insensitive substring matching — intentionally lenient so
    that chunked documents still count as hits when they contain the key
    phrase.
    """
    lower = retrieved_text.lower()
    return any(snippet.lower() in lower for snippet in relevant_snippets)


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------


def reciprocal_rank(retrieved: List[str], relevant_snippets: List[str]) -> float:
    """1 / (position of first relevant result).  0 if none found."""
    for i, doc in enumerate(retrieved, start=1):
        if _is_relevant(doc, relevant_snippets):
            return 1.0 / i
    return 0.0


def recall_at_k(
    retrieved: List[str], relevant_snippets: List[str], k: int
) -> float:
    """Fraction of relevant snippets covered by the top-K results."""
    if not relevant_snippets:
        return 1.0
    top_k = retrieved[:k]
    combined = " ".join(top_k).lower()
    hits = sum(1 for s in relevant_snippets if s.lower() in combined)
    return hits / len(relevant_snippets)


def precision_at_k(
    retrieved: List[str], relevant_snippets: List[str], k: int
) -> float:
    """Fraction of top-K documents that are relevant."""
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    relevant_count = sum(1 for doc in top_k if _is_relevant(doc, relevant_snippets))
    return relevant_count / len(top_k)


# ---------------------------------------------------------------------------
# Retriever interfaces
# ---------------------------------------------------------------------------


class Retriever:
    """Abstract retriever that returns a ranked list of text chunks."""

    def search(self, query: str, k: int = 10) -> List[str]:
        raise NotImplementedError


class MockRetriever(Retriever):
    """Returns synthetic chunks that partially overlap with ground truth.

    Useful for exercising the metrics pipeline without any ML deps.
    """

    MOCK_CORPUS = [
        "Check-in is from 3:00 PM. Early check-in is available based on lair readiness.",
        "Checkout is by 11:00 AM. Late checkout may incur a small broomstick fee.",
        "PET POLICY: Bats (unlimited at Vampire Manor), Black cats (bring at least 13), "
        "Hellhounds (must be leashed after 9PM), Three-headed dogs (counts as one pet).",
        "VAMPIRE MANOR: ETERNAL NIGHT INN. Coffin Suites: Luxurious satin-lined resting chambers. "
        "Crypt Penthouses: Multi-room subterranean palaces. No-Mirror Suites available.",
        "WiFi: Network: \"Eternal_Connection\" Password: \"MUAHAHAHA666\" "
        "Complimentary high-speed (666 Mbps).",
        "Lunar Wellness Center: Full-Body Fur Grooming & Conditioning, "
        "Claw Sharpening & Polish, Howling Therapy Sessions, "
        "Post-Transformation Recovery Treatment.",
        "HALLOWEEN EXTRAVAGANZA (October 24-31). The Grand Halloween Ball: "
        "October 31st, Midnight-Dawn. Costume Contest. Monster Mash Dance-Off.",
        "CANCELLATION POLICY: 72 hours notice: Full refund. "
        "48-72 hours: 50% refund. No-show: Cursed for 7 years.",
        "Voltage Victuals Restaurant: Electric Eel Carpaccio, "
        "Shock-and-Awe Steak, Frankenstein's Feast.",
        "The Monster Resort features a heated pool and three themed restaurants.",
        "Standard Check-In Times and Standard Check-Out Times vary by property.",
        "Room service is available 24/7.",
        "ZOMBIE BED & BREAKFAST: Can I check in if I'm not a zombie? "
        "Non-zombies welcome! Heavily discounted rates for humans. "
        "Complimentary monster makeover package included.",
        "THE MUMMY RESORT: Eternal Preservation Spa. "
        "Sand Exfoliation Treatment (authentic Sahara grains), "
        "Papyrus Wrap Therapy, Hieroglyphic Henna Body Art, "
        "Resin & Natron Deep Tissue Massage, "
        "Tomb Temperature Stone Therapy (cooled to 55°F).",
        "VALENTINE'S DARK HEARTS WEEKEND: VAMPIRE MANOR - Eternal Love: "
        "Couples coffin (king-sized), Crimson elixir & roses ceremony, "
        "Moonlight flight for two. The Eternal Romance Package.",
        "PAYMENT METHODS: All major credit cards, Cryptocurrency "
        "(BitCoffin, EtherGhost), PayPal (for modern monsters). "
        "Not Accepted: Human souls (regulatory issues).",
        "How far in advance should I book? Halloween week: 6 months. "
        "Book by: September 1st (sells out every year!). "
        "Full moon weekends (Werewolf Lodge): 3 months.",
    ]

    def search(self, query: str, k: int = 10) -> List[str]:
        """Rudimentary keyword overlap ranking."""
        query_tokens = set(query.lower().split())
        scored = []
        for doc in self.MOCK_CORPUS:
            doc_tokens = set(doc.lower().split())
            overlap = len(query_tokens & doc_tokens)
            scored.append((overlap, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:k]]


class LiveRetriever(Retriever):
    """Wraps the real VectorRAG / AdvancedRAG pipeline."""

    def __init__(self):
        self._rag = None

    def _ensure_init(self):
        if self._rag is not None:
            return

        knowledge_dir = PROJECT_ROOT / "data" / "knowledge"
        persist_dir = str(PROJECT_ROOT / ".rag_store")

        # Try AdvancedRAG first, fall back to VectorRAG
        try:
            from app.rag.advanced_rag import AdvancedRAG

            self._rag = AdvancedRAG(persist_dir, "knowledge")
        except ImportError:
            from app.rag.vector_rag import VectorRAG

            self._rag = VectorRAG(persist_dir, "knowledge")

        # Ingest if collection is empty
        if self._rag.collection.count() == 0:
            self._rag.ingest_folder(str(knowledge_dir))

    def search(self, query: str, k: int = 10) -> List[str]:
        self._ensure_init()
        result = self._rag.search(query, k=k)
        return [r["text"] for r in result.get("results", [])]


# ---------------------------------------------------------------------------
# Evaluation driver
# ---------------------------------------------------------------------------


def evaluate_retrieval(
    ground_truth_path: Path,
    retriever: Retriever,
    max_k: int = 10,
) -> RetrievalReport:
    """Run all ground-truth queries and compute aggregate metrics."""

    with open(ground_truth_path) as f:
        raw = json.load(f)

    cases = [GroundTruthCase(**c) for c in raw]
    per_query: List[QueryMetrics] = []

    for case in cases:
        retrieved = retriever.search(case.query, k=max_k)

        rr = reciprocal_rank(retrieved, case.relevant_snippets)
        r3 = recall_at_k(retrieved, case.relevant_snippets, 3)
        r5 = recall_at_k(retrieved, case.relevant_snippets, 5)
        r10 = recall_at_k(retrieved, case.relevant_snippets, 10)
        p3 = precision_at_k(retrieved, case.relevant_snippets, 3)
        p5 = precision_at_k(retrieved, case.relevant_snippets, 5)
        p10 = precision_at_k(retrieved, case.relevant_snippets, 10)

        combined = " ".join(retrieved).lower()
        found = sum(1 for s in case.relevant_snippets if s.lower() in combined)

        per_query.append(
            QueryMetrics(
                query_id=case.id,
                query=case.query,
                reciprocal_rank=round(rr, 4),
                recall_at_3=round(r3, 4),
                recall_at_5=round(r5, 4),
                recall_at_10=round(r10, 4),
                precision_at_3=round(p3, 4),
                precision_at_5=round(p5, 4),
                precision_at_10=round(p10, 4),
                num_retrieved=len(retrieved),
                num_relevant_found=found,
                num_relevant_total=len(case.relevant_snippets),
            )
        )

    n = len(per_query)
    report = RetrievalReport(
        mrr=round(sum(q.reciprocal_rank for q in per_query) / n, 4) if n else 0.0,
        recall_at_3=round(sum(q.recall_at_3 for q in per_query) / n, 4) if n else 0.0,
        recall_at_5=round(sum(q.recall_at_5 for q in per_query) / n, 4) if n else 0.0,
        recall_at_10=round(sum(q.recall_at_10 for q in per_query) / n, 4) if n else 0.0,
        precision_at_3=round(sum(q.precision_at_3 for q in per_query) / n, 4)
        if n
        else 0.0,
        precision_at_5=round(sum(q.precision_at_5 for q in per_query) / n, 4)
        if n
        else 0.0,
        precision_at_10=round(sum(q.precision_at_10 for q in per_query) / n, 4)
        if n
        else 0.0,
        num_queries=n,
        per_query=per_query,
    )
    return report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_report(report: RetrievalReport) -> None:
    def pct(v: float) -> str:
        return f"{v * 100:.1f}%"  # noqa: E231

    print("\n=== Retrieval Quality Report ===")
    print(f"Queries evaluated: {report.num_queries}")
    print(f"\nMRR (Mean Reciprocal Rank): {report.mrr:.4f}")  # noqa: E231
    print("\nRecall@K:")
    print(f"  Recall@3:  {pct(report.recall_at_3)}")  # noqa: E241
    print(f"  Recall@5:  {pct(report.recall_at_5)}")  # noqa: E241
    print(f"  Recall@10: {pct(report.recall_at_10)}")
    print("\nPrecision@K:")
    print(f"  Precision@3:  {pct(report.precision_at_3)}")  # noqa: E241
    print(f"  Precision@5:  {pct(report.precision_at_5)}")  # noqa: E241
    print(f"  Precision@10: {pct(report.precision_at_10)}")

    print("\nPer-Query Breakdown:")
    print(
        f"  {'ID':>3}  {'RR':>5}  {'R@3':>5}  {'R@5':>5}  {'R@10':>5}  "  # noqa: E231
        f"{'P@3':>5}  {'P@5':>5}  {'P@10':>5}  Query"  # noqa: E231
    )
    print(
        f"  {'---':>3}  {'---':>5}  {'---':>5}  {'---':>5}  {'-----':>5}  "  # noqa: E231
        f"{'---':>5}  {'---':>5}  {'-----':>5}  {'-----'}"  # noqa: E231
    )
    for q in report.per_query:
        print(
            f"  {q.query_id:>3}  {q.reciprocal_rank:>5.2f}  "  # noqa: E231
            f"{q.recall_at_3:>5.2f}  {q.recall_at_5:>5.2f}  {q.recall_at_10:>5.2f}  "  # noqa: E231
            f"{q.precision_at_3:>5.2f}  {q.precision_at_5:>5.2f}  {q.precision_at_10:>5.2f}  "  # noqa: E231
            f"{q.query[:45]}"
        )
    print()


def _get_git_sha() -> str:
    """Return short git commit SHA, or 'unknown' if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


_METRIC_KEYS = [
    "mrr", "recall_at_3", "recall_at_5", "recall_at_10",
    "precision_at_3", "precision_at_5", "precision_at_10",
]

_PASS_THRESHOLDS = {"mrr": 0.5, "recall_at_5": 0.5}


def _build_metrics_dict(report: RetrievalReport) -> dict:
    return {k: getattr(report, k) for k in _METRIC_KEYS}


def _passes(metrics: dict) -> bool:
    return all(metrics.get(k, 0) >= v for k, v in _PASS_THRESHOLDS.items())


def save_report(report: RetrievalReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mrr": report.mrr,
        "recall_at_3": report.recall_at_3,
        "recall_at_5": report.recall_at_5,
        "recall_at_10": report.recall_at_10,
        "precision_at_3": report.precision_at_3,
        "precision_at_5": report.precision_at_5,
        "precision_at_10": report.precision_at_10,
        "num_queries": report.num_queries,
        "per_query": [asdict(q) for q in report.per_query],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Report saved to {output_path}")

    metrics = _build_metrics_dict(report)
    history_path = output_path.parent / "eval_history.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        **metrics,
        "num_queries": report.num_queries,
        "pass": _passes(metrics),
    }
    with open(history_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Run appended to {history_path}")


def compare_last(history_path: Path) -> None:
    """Load last two JSONL entries and print a delta."""
    if not history_path.exists():
        print("No eval history found.")
        return

    lines = history_path.read_text().strip().splitlines()
    if len(lines) < 2:
        print("Need at least 2 runs in history to compare.")
        return

    try:
        prev = json.loads(lines[-2])
        curr = json.loads(lines[-1])
    except json.JSONDecodeError:
        print("Error: corrupted history entries. Re-run to generate fresh data.")
        return

    print("\n=== Eval Comparison (last two runs) ===")
    print(f"  Previous: {prev.get('git_sha', '?')}  @ {prev.get('timestamp', '?')}")  # noqa: E241
    print(f"  Current:  {curr.get('git_sha', '?')}  @ {curr.get('timestamp', '?')}")  # noqa: E241
    print()

    for key in _METRIC_KEYS:
        old_val = prev.get(key, 0.0)
        new_val = curr.get(key, 0.0)
        delta = new_val - old_val
        if abs(delta) < 1e-6:
            status = "unchanged"
        elif delta > 0:
            status = f"improved  (+{delta:.4f})"  # noqa: E231
        else:
            status = f"degraded  ({delta:.4f})"  # noqa: E231
        print(f"  {key:<16} {old_val:.4f} -> {new_val:.4f}  {status}")  # noqa: E231

    prev_pass = prev.get("pass", False)
    curr_pass = curr.get("pass", False)
    print(f"\n  Pass status: {'PASS' if prev_pass else 'FAIL'} -> {'PASS' if curr_pass else 'FAIL'}")
    print()


def show_history(history_path: Path) -> None:
    """Print all historical runs as a timeline."""
    if not history_path.exists():
        print("No eval history found.")
        return

    lines = history_path.read_text().strip().splitlines()
    print(f"\n=== Retrieval Eval History ({len(lines)} runs) ===\n")
    print(
        f"  {'#':>3}  {'Date':>10}  {'SHA':>8}  "  # noqa: E231
        f"{'MRR':>6}  {'R@5':>6}  {'Pass':>5}"  # noqa: E231
    )
    print(f"  {'─' * 3}  {'─' * 10}  {'─' * 8}  {'─' * 6}  {'─' * 6}  {'─' * 5}")  # noqa: E231

    for i, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {i:>3}  [corrupted entry — skipped]")  # noqa: E231
            continue
        ts = entry.get("timestamp", "?")[:10]
        sha = entry.get("git_sha", "?")
        mrr = entry.get("mrr", 0.0)
        r5 = entry.get("recall_at_5", 0.0)
        passed = "PASS" if entry.get("pass", False) else "FAIL"
        print(f"  {i:>3}  {ts}  {sha:>8}  {mrr:>6.4f}  {r5:>6.4f}  {passed:>5}")  # noqa: E231

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval quality with IR metrics"
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=PROJECT_ROOT / "evals" / "retrieval_ground_truth.json",
        help="Path to ground-truth JSON file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "retrieval_metrics.json",
        help="Path to write the JSON report",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Use the real RAG pipeline (requires chromadb + sentence-transformers)",
    )
    parser.add_argument(
        "--max-k",
        type=int,
        default=10,
        help="Maximum K for retrieval (default: 10)",
    )
    parser.add_argument(
        "--compare-last",
        action="store_true",
        default=False,
        help="Print metric deltas between the two most recent eval runs",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        default=False,
        help="Show full run history",
    )
    args = parser.parse_args()

    history_path = args.output.parent / "eval_history.jsonl"

    if args.compare_last:
        compare_last(history_path)
        return

    if args.history:
        show_history(history_path)
        return

    retriever: Retriever
    if args.live:
        retriever = LiveRetriever()
    else:
        retriever = MockRetriever()

    report = evaluate_retrieval(args.ground_truth, retriever, max_k=args.max_k)
    print_report(report)
    save_report(report, args.output)


if __name__ == "__main__":
    main()
