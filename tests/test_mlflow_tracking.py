"""Tests for MLflow tracking integration."""

import pytest
from unittest.mock import MagicMock, patch
from app.monitoring.mlflow_tracking import MLflowTracker
from app.validation.hallucination import ConfidenceResult, ConfidenceLevel


class TestMLflowTrackerDisabled:
    def test_noop_when_disabled(self):
        tracker = MLflowTracker(enabled=False)
        assert tracker.enabled is False

        # All methods should silently do nothing
        tracker.log_rag_evaluation("query", [], 10.0)
        tracker.log_model_config({"model": "gpt-4o"})
        tracker.log_confidence_metrics(
            ConfidenceResult(0.8, ConfidenceLevel.HIGH, 0.7, 0.9, 0.6),
            provider="openai",
        )
        tracker.log_benchmark_results("test", {"latency": 100.0})

    def test_disabled_when_mlflow_not_installed(self):
        with patch.dict("sys.modules", {"mlflow": None}):
            tracker = MLflowTracker(
                enabled=True, tracking_uri="http://fake:5000"
            )
            assert tracker.enabled is False


class TestMLflowTrackerEnabled:
    @pytest.fixture
    def mock_mlflow(self):
        mock = MagicMock()
        mock.start_run.return_value.__enter__ = MagicMock()
        mock.start_run.return_value.__exit__ = MagicMock(return_value=False)
        return mock

    @pytest.fixture
    def tracker(self, mock_mlflow):
        t = MLflowTracker(enabled=False)
        t.enabled = True
        t._mlflow = mock_mlflow
        return t

    def test_log_rag_evaluation(self, tracker, mock_mlflow):
        tracker.log_rag_evaluation(
            query="vampire amenities",
            results=[{"text": "gothic pool", "score": 0.95}],
            latency_ms=42.0,
            rag_type="advanced",
        )
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_param.assert_any_call("rag_type", "advanced")
        mock_mlflow.log_metric.assert_any_call("latency_ms", 42.0)

    def test_log_model_config(self, tracker, mock_mlflow):
        tracker.log_model_config({"provider": "openai", "model": "gpt-4o"})
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_param.assert_any_call("provider", "openai")

    def test_log_confidence_metrics(self, tracker, mock_mlflow):
        result = ConfidenceResult(
            overall_score=0.85,
            level=ConfidenceLevel.HIGH,
            context_overlap_score=0.7,
            semantic_similarity_score=0.95,
            source_attribution_score=0.8,
        )
        tracker.log_confidence_metrics(result, provider="openai")
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_metric.assert_any_call("confidence_overall", 0.85)

    def test_log_benchmark_results(self, tracker, mock_mlflow):
        tracker.log_benchmark_results(
            benchmark_name="hybrid_vs_dense",
            metrics={"avg_latency_ms": 50.0, "avg_results": 4.5},
            params={"bm25_weight": "0.4"},
        )
        mock_mlflow.start_run.assert_called_once()
        mock_mlflow.log_metrics.assert_called_once_with(
            {"avg_latency_ms": 50.0, "avg_results": 4.5}
        )
