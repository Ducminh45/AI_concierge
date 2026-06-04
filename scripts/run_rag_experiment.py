#!/usr/bin/env python3
"""RAG experiment runner with persistent result tracking.

Runs RAG evaluation experiments with different configurations
and logs results to MLflow + JSONL history for comparison.

Usage:
    python scripts/run_rag_experiment.py               # run experiments, save to JSONL
    python scripts/run_rag_experiment.py --compare-last # diff last 2 runs
    python scripts/run_rag_experiment.py --history      # show full history
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.advanced_rag import AdvancedRAG  # noqa: E402
from app.monitoring.mlflow_tracking import MLflowTracker  # noqa: E402

HISTORY_PATH = Path(__file__).resolve().parent.parent / "reports" / "rag_experiment_history.jsonl"

BENCHMARK_QUERIES = [
    "What amenities does Vampire Manor offer?",
    "Tell me about the Werewolf Lodge pool",
    "Does Castle Frankenstein have room service?",
    "What is the check-in time at Zombie B&B?",
    "Are there spa services at the Mummy Resort?",
    "What dining options are available at Ghostly B&B?",
    "Is there a gym at Vampire Manor?",
    "What is the cancellation policy?",
]


# ---------------------------------------------------------------------------
# Experiment logic
# ---------------------------------------------------------------------------


def run_experiment(
    rag: AdvancedRAG,
    tracker: MLflowTracker,
    queries: list[str],
    config_name: str,
    bm25_weight: float = 0.4,
    use_reranker: bool = True,
) -> dict:
    """Run a set of queries and return aggregated metrics."""
    print(f"\n{'=' * 60}")
    print(f"Experiment: {config_name}")
    print(f"BM25 weight: {bm25_weight}, Reranker: {use_reranker}")
    print(f"{'=' * 60}")

    total_latency = 0
    total_results = 0

    for query in queries:
        start = time.perf_counter()
        results = rag.search(
            query, k=5, bm25_weight=bm25_weight, use_reranker=use_reranker
        )
        latency_ms = (time.perf_counter() - start) * 1000
        total_latency += latency_ms

        result_list = results.get("results", [])
        total_results += len(result_list)
        top_score = result_list[0]["score"] if result_list else 0.0

        print(
            f"  Query: {query[:50]}... | {len(result_list)} results | "  # noqa: E231
            f"top_score={top_score:.3f} | {latency_ms:.1f}ms"  # noqa: E231
        )

        tracker.log_rag_evaluation(
            query=query,
            results=result_list,
            latency_ms=latency_ms,
            rag_type=config_name,
            extra_params={
                "bm25_weight": str(bm25_weight),
                "use_reranker": str(use_reranker),
            },
        )

    avg_latency = round(total_latency / len(queries), 2)
    avg_results = round(total_results / len(queries), 2)

    tracker.log_benchmark_results(
        benchmark_name=config_name,
        metrics={"avg_latency_ms": avg_latency, "avg_results": avg_results},
        params={
            "bm25_weight": str(bm25_weight),
            "use_reranker": str(use_reranker),
        },
    )

    print(f"\n  Average latency: {avg_latency:.1f}ms")  # noqa: E231
    print(f"  Average results: {avg_results:.1f}")  # noqa: E231

    return {
        "config": config_name,
        "bm25_weight": bm25_weight,
        "use_reranker": use_reranker,
        "avg_latency_ms": avg_latency,
        "avg_results": avg_results,
    }


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


def save_run(experiment_results: list[dict]) -> None:
    """Append this run to the JSONL history file."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    configs = {}
    for r in experiment_results:
        configs[r["config"]] = {
            "avg_latency_ms": r["avg_latency_ms"],
            "avg_results": r["avg_results"],
        }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "num_queries": len(BENCHMARK_QUERIES),
        "num_configs": len(experiment_results),
        "configs": configs,
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\nRun appended to {HISTORY_PATH}")


def compare_last() -> None:
    """Print deltas between the two most recent runs."""
    if not HISTORY_PATH.exists():
        print("No experiment history found.")
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

    print("\n=== RAG Experiment Comparison (last two runs) ===")
    print(f"  Previous: {prev['git_sha']}  @ {prev['timestamp']}")  # noqa: E231
    print(f"  Current:  {curr['git_sha']}  @ {curr['timestamp']}")  # noqa: E231

    prev_configs = prev.get("configs", {})
    curr_configs = curr.get("configs", {})
    all_names = list(dict.fromkeys(
        list(prev_configs.keys()) + list(curr_configs.keys())
    ))

    print(f"\n  {'Config':<25} {'Prev Latency':>14} {'Curr Latency':>14} {'Delta':>10}")  # noqa: E231
    print(f"  {'─' * 25} {'─' * 14} {'─' * 14} {'─' * 10}")  # noqa: E231

    for name in all_names:
        p = prev_configs.get(name, {})
        c = curr_configs.get(name, {})
        p_lat = p.get("avg_latency_ms", 0.0)
        c_lat = c.get("avg_latency_ms", 0.0)
        delta = c_lat - p_lat
        sign = "+" if delta > 0 else ""
        print(f"  {name:<25} {p_lat:>12.1f}ms {c_lat:>12.1f}ms {sign}{delta:>8.1f}ms")  # noqa: E231

    print()


def show_history() -> None:
    """Print all historical runs."""
    if not HISTORY_PATH.exists():
        print("No experiment history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    print(f"\n=== RAG Experiment History ({len(lines)} runs) ===\n")

    for i, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {i:>3}  [corrupted entry — skipped]")  # noqa: E231
            continue
        ts = entry["timestamp"][:10]
        sha = entry["git_sha"]
        configs = entry.get("configs", {})
        summary = ", ".join(
            f"{k}={v.get('avg_latency_ms', 0):.0f}ms"  # noqa: E231
            for k, v in configs.items()
        )
        print(f"  {i:>3}  {ts}  {sha}  {summary}")  # noqa: E231

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Run RAG experiments with different configurations"
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

    persist_dir = os.environ.get("RAG_PERSIST_DIR", "./.rag_store")
    collection = os.environ.get("RAG_COLLECTION", "monster_resort_knowledge")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow_enabled = os.environ.get("MLFLOW_ENABLED", "true").lower() == "true"

    tracker = MLflowTracker(
        tracking_uri=mlflow_uri,
        experiment_name="rag-experiments",
        enabled=mlflow_enabled,
    )

    rag = AdvancedRAG(persist_dir, collection)

    knowledge_path = Path.cwd() / "data" / "knowledge"
    if knowledge_path.exists():
        print(f"Ingesting knowledge from {knowledge_path}...")
        rag.ingest_folder(str(knowledge_path))

    configs = [
        ("hybrid_reranked", 0.4, True),
        ("dense_reranked", 0.0, True),
        ("bm25_heavy_reranked", 0.7, True),
        ("hybrid_no_reranker", 0.4, False),
    ]

    all_results = []
    for config_name, bm25_w, rerank in configs:
        result = run_experiment(
            rag, tracker, BENCHMARK_QUERIES, config_name,
            bm25_weight=bm25_w, use_reranker=rerank,
        )
        all_results.append(result)

    save_run(all_results)

    print("\nAll experiments complete!")
    if mlflow_enabled:
        print(f"View results at: {mlflow_uri}")


if __name__ == "__main__":
    main()
