"""Retrieval ablation: BM25 vs Dense vs Hybrid vs Full pipeline on the resort knowledge base."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.advanced_rag import AdvancedRAG  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "knowledge"
GROUND_TRUTH_PATH = PROJECT_ROOT / "evals" / "retrieval_ground_truth.json"
REPORT_DIR = PROJECT_ROOT / "reports"
REPORT_PATH = REPORT_DIR / "retrieval_ablation.json"
# Use a dedicated store so we don't pollute the app store
ABLATION_STORE = str(PROJECT_ROOT / ".ablation_rag_store")

COLLECTION = "ablation_test"

# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def load_ground_truth() -> List[Dict]:
    if GROUND_TRUTH_PATH.exists():
        with open(GROUND_TRUTH_PATH) as f:
            return json.load(f)
    return []


def default_queries() -> List[str]:
    return [
        "What are the check-in and checkout times?",
        "What is the pet policy?",
        "Tell me about Vampire Manor rooms and coffins",
        "What is the WiFi password?",
        "What spa services does the Werewolf Lodge offer?",
        "What happens during the Halloween event?",
        "What is the cancellation and refund policy?",
        "What dining options does Castle Frankenstein have?",
    ]


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_texts: List[str], relevant_snippets: List[str], k: int = 5) -> float:
    """Fraction of top-k retrieved docs that contain at least one relevant snippet."""
    if not relevant_snippets:
        return 0.0
    top_k = retrieved_texts[:k]
    hits = 0
    for text in top_k:
        text_lower = text.lower()
        if any(snip.lower() in text_lower for snip in relevant_snippets):
            hits += 1
    return hits / min(k, max(len(top_k), 1))


def mean_reciprocal_rank(retrieved_texts: List[str], relevant_snippets: List[str]) -> float:
    """1 / rank of first relevant result (0 if none found)."""
    if not relevant_snippets:
        return 0.0
    for rank, text in enumerate(retrieved_texts, start=1):
        text_lower = text.lower()
        if any(snip.lower() in text_lower for snip in relevant_snippets):
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------------------
# Retrieval configurations
# ---------------------------------------------------------------------------

def run_bm25_only(rag: AdvancedRAG, query: str, k: int = 5) -> List[Dict]:
    """BM25 keyword search only."""
    raw = rag._bm25_search(query, k=k)
    results = []
    for idx, score in raw[:k]:
        results.append({"text": rag.corpus[idx], "score": score})
    return results


def run_dense_only(rag: AdvancedRAG, query: str, k: int = 5) -> List[Dict]:
    """Dense embedding search only (ChromaDB)."""
    pairs = rag._dense_search(query, k=k)
    return [{"text": t, "score": s} for t, s in pairs[:k]]


def run_hybrid_no_reranker(rag: AdvancedRAG, query: str, k: int = 5) -> List[Dict]:
    """Hybrid BM25 + dense with RRF, no reranker."""
    result = rag.search(query, k=k, use_reranker=False)
    return result.get("results", [])[:k]


def run_full_pipeline(rag: AdvancedRAG, query: str, k: int = 5) -> List[Dict]:
    """Full pipeline: hybrid + cross-encoder reranker."""
    result = rag.search(query, k=k, use_reranker=True)
    return result.get("results", [])[:k]


CONFIGS = {
    "BM25 only": run_bm25_only,
    "Dense only": run_dense_only,
    "Hybrid (no reranker)": run_hybrid_no_reranker,
    "Full pipeline": run_full_pipeline,
}


# ---------------------------------------------------------------------------
# Main ablation
# ---------------------------------------------------------------------------

def run_ablation() -> Dict:
    print("=" * 60)
    print("RETRIEVAL ABLATION STUDY")
    print("=" * 60)

    # --- Initialize RAG and ingest knowledge ---
    print("\n[1/3] Initializing RAG system and ingesting knowledge...")
    rag = AdvancedRAG(
        persist_dir=ABLATION_STORE,
        collection=COLLECTION,
        embedding_model="all-MiniLM-L6-v2",
        reranker_model="BAAI/bge-reranker-base",
    )

    if rag.collection.count() == 0:
        print(f"      Ingesting from {KNOWLEDGE_DIR} ...")
        count = rag.ingest_folder(str(KNOWLEDGE_DIR))
        print(f"      Ingested {count} chunks")
    else:
        print(f"      Collection already has {rag.collection.count()} documents")

    # --- Load ground truth and queries ---
    ground_truth = load_ground_truth()
    gt_map: Dict[str, List[str]] = {}
    queries: List[str] = []

    if ground_truth:
        for entry in ground_truth:
            gt_map[entry["query"]] = entry["relevant_snippets"]
            queries.append(entry["query"])
        print(f"\n      Loaded {len(ground_truth)} ground-truth entries")
    else:
        queries = default_queries()
        print("\n      No ground truth found; using default queries (no P@5/MRR)")

    # --- Run ablation ---
    print("\n[2/3] Running retrieval ablation across 4 configs...")
    results: Dict[str, Dict] = {}

    for config_name, retrieval_fn in CONFIGS.items():
        print(f"\n  >> {config_name}")
        config_metrics = {
            "latencies_ms": [],
            "result_counts": [],
            "precisions": [],
            "mrrs": [],
            "per_query": [],
        }

        for query in queries:
            t0 = time.perf_counter()
            docs = retrieval_fn(rag, query, k=5)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            texts = [d["text"] for d in docs]
            snippets = gt_map.get(query, [])

            p5 = precision_at_k(texts, snippets, k=5) if snippets else None
            mrr = mean_reciprocal_rank(texts, snippets) if snippets else None

            config_metrics["latencies_ms"].append(elapsed_ms)
            config_metrics["result_counts"].append(len(docs))
            if p5 is not None:
                config_metrics["precisions"].append(p5)
            if mrr is not None:
                config_metrics["mrrs"].append(mrr)

            config_metrics["per_query"].append({
                "query": query,
                "latency_ms": round(elapsed_ms, 2),
                "num_results": len(docs),
                "precision_at_5": round(p5, 4) if p5 is not None else None,
                "mrr": round(mrr, 4) if mrr is not None else None,
                "top_result_preview": texts[0][:120] if texts else "(none)",
            })

        n = len(config_metrics["latencies_ms"])
        avg_latency = sum(config_metrics["latencies_ms"]) / n if n else 0
        avg_results = sum(config_metrics["result_counts"]) / n if n else 0
        avg_p5 = (
            sum(config_metrics["precisions"]) / len(config_metrics["precisions"])
            if config_metrics["precisions"]
            else None
        )
        avg_mrr = (
            sum(config_metrics["mrrs"]) / len(config_metrics["mrrs"])
            if config_metrics["mrrs"]
            else None
        )

        results[config_name] = {
            "avg_latency_ms": round(avg_latency, 2),
            "avg_result_count": round(avg_results, 1),
            "avg_precision_at_5": round(avg_p5, 4) if avg_p5 is not None else None,
            "avg_mrr": round(avg_mrr, 4) if avg_mrr is not None else None,
            "per_query": config_metrics["per_query"],
        }
        print(f"     avg latency: {avg_latency:.1f} ms | avg P@5: {avg_p5 or 'N/A'} | avg MRR: {avg_mrr or 'N/A'}")

    return results


def print_markdown_table(results: Dict[str, Dict]) -> None:
    """Print a clean markdown comparison table."""
    has_gt = any(v["avg_precision_at_5"] is not None for v in results.values())

    print("\n\n## Retrieval Ablation Results\n")

    if has_gt:
        header = "| Config | Avg Latency (ms) | Avg Results | Precision@5 | MRR |"
        sep =    "|--------|----------------:|------------:|------------:|----:|"
    else:
        header = "| Config | Avg Latency (ms) | Avg Results |"
        sep =    "|--------|----------------:|------------:|"

    print(header)
    print(sep)

    for name, m in results.items():
        lat = f"{m['avg_latency_ms']:.1f}"
        cnt = f"{m['avg_result_count']:.0f}"
        if has_gt:
            p5 = f"{m['avg_precision_at_5']:.4f}" if m["avg_precision_at_5"] is not None else "N/A"
            mrr = f"{m['avg_mrr']:.4f}" if m["avg_mrr"] is not None else "N/A"
            print(f"| {name} | {lat} | {cnt} | {p5} | {mrr} |")
        else:
            print(f"| {name} | {lat} | {cnt} |")


def save_report(results: Dict[str, Dict]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_ablation()
    print_markdown_table(results)
    save_report(results)
    print("\nDone.")
