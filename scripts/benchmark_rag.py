#!/usr/bin/env python3
"""Benchmarks AdvancedRAG vs LangChain RAG on latency and result quality.

Results are appended to a JSONL history file for tracking over time.

Usage:
    python scripts/benchmark_rag.py               # run benchmark, save to JSONL
    python scripts/benchmark_rag.py --compare-last # diff last 2 runs
    python scripts/benchmark_rag.py --history      # show full history
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.advanced_rag import AdvancedRAG  # noqa: E402
from app.rag.langchain_rag import LangChainRAG  # noqa: E402
from app.monitoring.mlflow_tracking import MLflowTracker  # noqa: E402

HISTORY_PATH = Path(__file__).resolve().parent.parent / "reports" / "benchmark_rag_history.jsonl"

BENCHMARK_QUERIES = [
    "What amenities does Vampire Manor offer?",
    "Tell me about the Werewolf Lodge pool",
    "Does Castle Frankenstein have room service?",
    "What is the check-in time at Zombie B&B?",
    "Are there spa services at the Mummy Resort?",
]


# ---------------------------------------------------------------------------
# Benchmark logic
# ---------------------------------------------------------------------------


def benchmark_rag(rag, name: str, queries: list[str]) -> dict:
    """Run queries against a RAG system and return metrics."""
    latencies = []
    result_counts = []
    top_scores = []

    for query in queries:
        start = time.perf_counter()
        results = rag.search(query, k=5)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        result_list = results.get("results", [])
        result_counts.append(len(result_list))
        if result_list:
            top_scores.append(result_list[0].get("score", 0.0))

    return {
        "name": name,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        "max_latency_ms": round(max(latencies), 2),
        "min_latency_ms": round(min(latencies), 2),
        "avg_results": round(sum(result_counts) / len(result_counts), 2),
        "avg_top_score": round(
            sum(top_scores) / len(top_scores) if top_scores else 0.0, 4
        ),
    }


def print_comparison(custom: dict, langchain: dict):
    """Print a comparison table."""
    print("\n" + "=" * 70)
    print("RAG BENCHMARK COMPARISON")
    print("=" * 70)
    print(f"{'Metric':<30} {'Custom AdvancedRAG':>18} {'LangChain RAG':>18}")  # noqa: E231
    print("-" * 70)

    metrics = [
        ("Avg Latency (ms)", "avg_latency_ms"),
        ("Max Latency (ms)", "max_latency_ms"),
        ("Min Latency (ms)", "min_latency_ms"),
        ("Avg Results Returned", "avg_results"),
        ("Avg Top Score", "avg_top_score"),
    ]

    for label, key in metrics:
        c_val = custom[key]
        l_val = langchain[key]
        print(f"{label:<30} {c_val:>18.2f} {l_val:>18.2f}")  # noqa: E231

    print("=" * 70)

    if custom["avg_latency_ms"] < langchain["avg_latency_ms"]:
        print("Winner (latency): Custom AdvancedRAG")
    else:
        print("Winner (latency): LangChain RAG")

    print()


# ---------------------------------------------------------------------------
# JSONL persistence
# ---------------------------------------------------------------------------


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def save_run(custom: dict, langchain: dict) -> None:
    """Append this benchmark run to the JSONL history."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "custom_rag": {k: v for k, v in custom.items() if k != "name"},
        "langchain_rag": {k: v for k, v in langchain.items() if k != "name"},
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"Run appended to {HISTORY_PATH}")


def compare_last() -> None:
    """Print deltas between the two most recent runs."""
    if not HISTORY_PATH.exists():
        print("No benchmark history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    if len(lines) < 2:
        print("Need at least 2 runs in history to compare.")
        return

    try:
        prev = json.loads(lines[-2])
        curr = json.loads(lines[-1])
    except json.JSONDecodeError:
        print("Error: corrupted history entries. Re-run to generate fresh data.")
        return

    print("\n=== RAG Benchmark Comparison (last two runs) ===")
    print(f"  Previous: {prev['git_sha']}  @ {prev['timestamp']}")  # noqa: E231
    print(f"  Current:  {curr['git_sha']}  @ {curr['timestamp']}")  # noqa: E231

    for rag_type in ["custom_rag", "langchain_rag"]:
        print(f"\n  {rag_type}:")  # noqa: E231
        p_data = prev.get(rag_type, {})
        c_data = curr.get(rag_type, {})
        for key in ["avg_latency_ms", "avg_top_score", "avg_results"]:
            old_val = p_data.get(key, 0.0)
            new_val = c_data.get(key, 0.0)
            delta = new_val - old_val
            sign = "+" if delta > 0 else ""
            print(f"    {key:<20} {old_val:>10.2f} -> {new_val:>10.2f}  ({sign}{delta:.2f})")  # noqa: E231

    print()


def show_history() -> None:
    """Print all historical runs."""
    if not HISTORY_PATH.exists():
        print("No benchmark history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    print(f"\n=== RAG Benchmark History ({len(lines)} runs) ===\n")

    for i, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {i:>3}  [corrupted entry — skipped]")  # noqa: E231
            continue
        ts = entry["timestamp"][:10]
        sha = entry["git_sha"]
        c_data = entry.get("custom_rag", {})
        l_data = entry.get("langchain_rag", {})
        print(
            f"  {i:>3}  {ts}  {sha}  "  # noqa: E231
            f"custom={c_data.get('avg_latency_ms', 0):.0f}ms  "  # noqa: E231
            f"langchain={l_data.get('avg_latency_ms', 0):.0f}ms"  # noqa: E231
        )

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark AdvancedRAG vs LangChain RAG"
    )
    parser.add_argument(
        "--compare-last", action="store_true",
        help="Print deltas between the two most recent runs",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Show full run history",
    )
    args = parser.parse_args()

    if args.compare_last:
        compare_last()
        return

    if args.history:
        show_history()
        return

    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow_enabled = os.environ.get("MLFLOW_ENABLED", "false").lower() == "true"

    tracker = MLflowTracker(
        tracking_uri=mlflow_uri,
        experiment_name="rag-benchmark",
        enabled=mlflow_enabled,
    )

    custom_dir = tempfile.mkdtemp(prefix="rag_custom_")
    langchain_dir = tempfile.mkdtemp(prefix="rag_langchain_")

    print("Initializing RAG systems...")
    custom_rag = AdvancedRAG(custom_dir, "benchmark_custom")
    langchain_rag = LangChainRAG(langchain_dir, "benchmark_langchain")

    knowledge_path = Path.cwd() / "data" / "knowledge"
    if knowledge_path.exists():
        print(f"Ingesting from {knowledge_path}...")
        custom_rag.ingest_folder(str(knowledge_path))
        langchain_rag.ingest_folder(str(knowledge_path))
    else:
        sample_texts = [
            "Vampire Manor offers eternal night ambiance with gothic towers, "
            "a moonlit infinity pool, and candlelit dining.",
            "The Werewolf Lodge features a heated outdoor pool surrounded by "
            "ancient oaks, moonlight yoga sessions, and a full-service spa.",
            "Castle Frankenstein provides high voltage luxury with 24-hour room "
            "service, an electrifying laboratory tour, and Tesla coil light shows.",
            "Zombie Bed & Breakfast has flexible check-in starting at 2 PM, "
            "complimentary brain-shaped pastries, and shambling garden walks.",
            "The Mummy Resort & Tomb-Service offers ancient Egyptian spa "
            "treatments, gold-leaf wrapping therapy, and sarcophagus "
            "meditation rooms.",
        ]
        print("Using sample data (no knowledge folder found)...")
        custom_rag.ingest_texts(sample_texts, source="benchmark")
        langchain_rag.ingest_texts(sample_texts, source="benchmark")

    print(f"\nRunning {len(BENCHMARK_QUERIES)} benchmark queries...")

    custom_metrics = benchmark_rag(
        custom_rag, "Custom AdvancedRAG", BENCHMARK_QUERIES
    )
    langchain_metrics = benchmark_rag(
        langchain_rag, "LangChain RAG", BENCHMARK_QUERIES
    )

    print_comparison(custom_metrics, langchain_metrics)
    save_run(custom_metrics, langchain_metrics)

    tracker.log_benchmark_results(
        "custom_advanced_rag",
        {k: v for k, v in custom_metrics.items() if isinstance(v, (int, float))},
        params={"rag_type": "custom_advanced"},
    )
    tracker.log_benchmark_results(
        "langchain_rag",
        {k: v for k, v in langchain_metrics.items() if isinstance(v, (int, float))},
        params={"rag_type": "langchain"},
    )

    print("Benchmark complete!")
    if mlflow_enabled:
        print(f"View results at: {mlflow_uri}")


if __name__ == "__main__":
    main()
