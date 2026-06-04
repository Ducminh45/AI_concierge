"""
MLflow MLOps Platform Integration
==================================

Provides experiment tracking for RAG evaluations, model configs,
confidence metrics, and benchmark results. Gracefully degrades
when mlflow is not installed or the server is unreachable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .logging_utils import logger


class MLflowTracker:
    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        experiment_name: str = "monster-resort-concierge",
        enabled: bool = False,
    ):
        self.enabled = enabled
        self._tracking_uri = tracking_uri
        self._experiment_name = experiment_name
        self._mlflow = None

        if enabled:
            try:
                import mlflow

                mlflow.set_tracking_uri(tracking_uri)
                mlflow.set_experiment(experiment_name)
                self._mlflow = mlflow
                logger.info(f"MLflow tracking enabled at {tracking_uri}")
            except ImportError:
                logger.warning("mlflow not installed — tracking disabled")
                self.enabled = False
            except Exception as e:
                logger.warning(f"MLflow setup failed: {e} — tracking disabled")
                self.enabled = False

    def log_rag_evaluation(
        self,
        query: str,
        results: List[Dict],
        latency_ms: float,
        rag_type: str = "advanced",
        extra_params: Optional[Dict] = None,
    ) -> None:
        """Log a single RAG query evaluation."""
        if not self.enabled:
            return

        try:
            with self._mlflow.start_run(nested=True):
                self._mlflow.log_param("rag_type", rag_type)
                self._mlflow.log_param("query", query[:250])
                self._mlflow.log_metric("latency_ms", latency_ms)
                self._mlflow.log_metric("num_results", len(results))
                if results:
                    self._mlflow.log_metric("top_score", results[0].get("score", 0.0))
                if extra_params:
                    self._mlflow.log_params(extra_params)
        except Exception as e:
            logger.warning(f"MLflow log_rag_evaluation failed: {e}")

    def log_model_config(self, config: Dict[str, Any]) -> None:
        """Log model/provider configuration as an MLflow run."""
        if not self.enabled:
            return

        try:
            with self._mlflow.start_run(nested=True):
                for k, v in config.items():
                    self._mlflow.log_param(k, str(v)[:250])
        except Exception as e:
            logger.warning(f"MLflow log_model_config failed: {e}")

    def log_confidence_metrics(
        self,
        confidence_result: Any,
        provider: str = "",
    ) -> None:
        """Log hallucination confidence metrics."""
        if not self.enabled:
            return

        try:
            with self._mlflow.start_run(nested=True):
                self._mlflow.log_param("provider", provider)
                self._mlflow.log_metric("confidence_overall", confidence_result.overall_score)
                self._mlflow.log_metric(
                    "confidence_overlap", confidence_result.context_overlap_score
                )
                self._mlflow.log_metric(
                    "confidence_semantic", confidence_result.semantic_similarity_score
                )
                self._mlflow.log_metric(
                    "confidence_attribution", confidence_result.source_attribution_score
                )
                self._mlflow.log_param("confidence_level", confidence_result.level.value)
        except Exception as e:
            logger.warning(f"MLflow log_confidence_metrics failed: {e}")

    def log_benchmark_results(
        self,
        benchmark_name: str,
        metrics: Dict[str, float],
        params: Optional[Dict[str, str]] = None,
    ) -> None:
        """Log RAG benchmark comparison results."""
        if not self.enabled:
            return

        try:
            with self._mlflow.start_run(run_name=benchmark_name, nested=True):
                if params:
                    self._mlflow.log_params(params)
                self._mlflow.log_metrics(metrics)
        except Exception as e:
            logger.warning(f"MLflow log_benchmark_results failed: {e}")
