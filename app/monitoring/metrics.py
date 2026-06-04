from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from .logging_utils import logger


# HTTP metrics
REQUEST_COUNT = Counter(
    "mrc_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_LATENCY = Histogram(
    "mrc_http_request_latency_seconds", "Request latency", ["path"]
)


def install_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as e:
            logger.error(f"Metrics middleware error: {e}")
            raise
        elapsed = time.perf_counter() - start
        path = request.url.path
        try:
            REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
            REQUEST_LATENCY.labels(path).observe(elapsed)
        except Exception as e:
            logger.error(f"Prometheus metrics error: {e}")
        return response

    @app.get("/metrics")
    def metrics():
        try:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return Response("Metrics unavailable", status_code=500)
