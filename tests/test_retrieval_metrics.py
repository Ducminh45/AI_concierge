"""Tests for retrieval quality metrics (evals/eval_retrieval.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evals.eval_retrieval import (  # noqa: E402
    MockRetriever,
    evaluate_retrieval,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


# ---------------------------------------------------------------------------
# Unit tests for individual metric functions
# ---------------------------------------------------------------------------


class TestReciprocalRank:
    def test_first_result_relevant(self):
        docs = ["relevant doc about pets", "other doc"]
        assert reciprocal_rank(docs, ["pets"]) == 1.0

    def test_second_result_relevant(self):
        docs = ["unrelated stuff", "relevant doc about pets", "more"]
        assert reciprocal_rank(docs, ["pets"]) == 0.5

    def test_no_relevant(self):
        docs = ["nothing here", "also nothing"]
        assert reciprocal_rank(docs, ["pets"]) == 0.0

    def test_empty_results(self):
        assert reciprocal_rank([], ["pets"]) == 0.0


class TestRecallAtK:
    def test_all_found_in_top_k(self):
        docs = ["doc with cats and dogs", "doc with birds"]
        assert recall_at_k(docs, ["cats", "dogs"], 2) == 1.0

    def test_partial_recall(self):
        docs = ["doc with cats only", "nothing relevant"]
        assert recall_at_k(docs, ["cats", "dogs"], 2) == 0.5

    def test_none_found(self):
        docs = ["nothing here"]
        assert recall_at_k(docs, ["cats", "dogs"], 1) == 0.0

    def test_empty_snippets(self):
        assert recall_at_k(["any doc"], [], 5) == 1.0


class TestPrecisionAtK:
    def test_all_relevant(self):
        docs = ["about cats", "about dogs"]
        assert precision_at_k(docs, ["cats", "dogs"], 2) == 1.0

    def test_half_relevant(self):
        docs = ["about cats", "about weather", "about dogs", "about sports"]
        assert precision_at_k(docs, ["cats", "dogs"], 4) == 0.5

    def test_none_relevant(self):
        docs = ["about weather", "about sports"]
        assert precision_at_k(docs, ["cats"], 2) == 0.0

    def test_k_larger_than_results(self):
        docs = ["about cats"]
        assert precision_at_k(docs, ["cats"], 5) == 1.0

    def test_empty_results(self):
        assert precision_at_k([], ["cats"], 3) == 0.0


# ---------------------------------------------------------------------------
# Integration: full eval pipeline with mock retriever
# ---------------------------------------------------------------------------


class TestEvaluateRetrieval:
    def test_mock_pipeline_runs(self, tmp_path: Path):
        gt_path = PROJECT_ROOT / "evals" / "retrieval_ground_truth.json"
        if not gt_path.exists():
            pytest.skip("Ground truth file not found")

        report = evaluate_retrieval(gt_path, MockRetriever(), max_k=10)

        assert report.num_queries > 0
        assert 0.0 <= report.mrr <= 1.0
        assert 0.0 <= report.recall_at_3 <= 1.0
        assert 0.0 <= report.recall_at_5 <= 1.0
        assert 0.0 <= report.recall_at_10 <= 1.0
        assert 0.0 <= report.precision_at_3 <= 1.0
        assert 0.0 <= report.precision_at_5 <= 1.0
        assert 0.0 <= report.precision_at_10 <= 1.0
        assert len(report.per_query) == report.num_queries

    def test_mock_retriever_has_nonzero_metrics(self):
        gt_path = PROJECT_ROOT / "evals" / "retrieval_ground_truth.json"
        if not gt_path.exists():
            pytest.skip("Ground truth file not found")

        report = evaluate_retrieval(gt_path, MockRetriever(), max_k=10)

        # The mock corpus is designed to produce nonzero metrics
        assert report.mrr > 0.0, "MRR should be > 0 with the mock retriever"
        assert report.recall_at_10 > 0.0, "Recall@10 should be > 0"
