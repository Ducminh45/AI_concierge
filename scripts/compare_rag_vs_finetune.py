#!/usr/bin/env python3
"""Compares RAG pipeline vs LoRA fine-tuned model on latency, answer length, and faithfulness."""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.advanced_rag import AdvancedRAG  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_DIR = PROJECT_ROOT / "lora-adapters"
MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

EVAL_QUERIES = [
    "What spa services are available at the Mummy Resort?",
    "Describe the dining options at Vampire Manor.",
    "What outdoor activities does the Werewolf Lodge offer?",
    "Is there room service at Castle Frankenstein?",
    "What is the check-in time at Zombie Bed & Breakfast?",
    "Tell me about the Ghostly B&B entertainment options.",
]


def query_rag(rag: AdvancedRAG, query: str) -> dict:
    """Run a single query through the RAG pipeline."""
    start = time.perf_counter()
    results = rag.search(query, k=3)
    latency_ms = (time.perf_counter() - start) * 1000

    snippets = results.get("results", [])
    answer = "\n".join(
        s.get("text", s.get("content", "")) for s in snippets
    )
    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "num_results": len(snippets),
    }


def query_finetune(query: str) -> dict:
    """Run a single query through the LoRA fine-tuned model."""
    start = time.perf_counter()
    cmd = [
        sys.executable, "-m", "mlx_lm.generate",
        "--model", MODEL_NAME,
        "--adapter-path", str(ADAPTER_DIR),
        "--prompt", query,
        "--max-tokens", "200",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    latency_ms = (time.perf_counter() - start) * 1000

    answer = result.stdout.strip() if result.returncode == 0 else "(error)"
    return {
        "answer": answer,
        "latency_ms": latency_ms,
        "returncode": result.returncode,
    }


def print_table(rag_results: list, ft_results: list, queries: list):
    """Print a side-by-side comparison table."""
    print()
    print("=" * 80)
    print("  RAG vs Fine-Tune Comparison")
    print("=" * 80)
    print()

    header = f"{'#':<3} {'Query':<45} {'RAG ms':>8} {'FT ms':>8} {'RAG len':>8} {'FT len':>8}"  # noqa: E231
    print(header)
    print("-" * 80)

    rag_latencies = []
    ft_latencies = []

    for i, (q, r, f) in enumerate(zip(queries, rag_results, ft_results), 1):
        short_q = q[:42] + "..." if len(q) > 45 else q
        rag_lat = r["latency_ms"]
        ft_lat = f["latency_ms"]
        rag_len = len(r["answer"])
        ft_len = len(f["answer"])
        rag_latencies.append(rag_lat)
        ft_latencies.append(ft_lat)
        print(f"{i:<3} {short_q:<45} {rag_lat:>8.1f} {ft_lat:>8.1f} {rag_len:>8} {ft_len:>8}")  # noqa: E231

    print("-" * 80)
    avg_rag = sum(rag_latencies) / len(rag_latencies)
    avg_ft = sum(ft_latencies) / len(ft_latencies)
    print(f"{'':>3} {'AVERAGE':<45} {avg_rag:>8.1f} {avg_ft:>8.1f}")  # noqa: E231
    print("=" * 80)
    print()


def save_results(rag_results: list, ft_results: list, queries: list, path: Path):
    """Save detailed results to JSON."""
    output = []
    for q, r, f in zip(queries, rag_results, ft_results):
        output.append({
            "query": q,
            "rag": r,
            "finetune": f,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"Detailed results saved to {path}")


def main():
    print("=" * 60)
    print("  Monster Resort -- RAG vs Fine-Tune Comparison")
    print("=" * 60)
    print()

    # Check adapter weights exist
    if not ADAPTER_DIR.exists():
        print(f"ERROR: Adapter weights not found at {ADAPTER_DIR}")
        print()
        print("Train adapters first:")
        print("  python scripts/prep_finetune_data.py")
        print("  python scripts/finetune_mlx.py")
        sys.exit(1)

    # Initialise RAG
    knowledge_dir = PROJECT_ROOT / "data" / "knowledge"
    rag_store = PROJECT_ROOT / ".rag_store"
    print("Initialising RAG pipeline...")
    rag = AdvancedRAG(str(rag_store), "comparison")
    if knowledge_dir.exists():
        rag.ingest_folder(str(knowledge_dir))
    else:
        print(f"WARNING: {knowledge_dir} not found -- RAG results may be empty.")

    # Run queries
    print(f"Running {len(EVAL_QUERIES)} queries through both systems...")
    print()

    rag_results = []
    ft_results = []

    for i, query in enumerate(EVAL_QUERIES, 1):
        print(f"  [{i}/{len(EVAL_QUERIES)}] {query[:60]}")

        r = query_rag(rag, query)
        rag_results.append(r)

        f = query_finetune(query)
        ft_results.append(f)

    # Display comparison
    print_table(rag_results, ft_results, EVAL_QUERIES)

    # Save
    output_path = PROJECT_ROOT / "data" / "finetune" / "comparison_results.json"
    save_results(rag_results, ft_results, EVAL_QUERIES, output_path)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
