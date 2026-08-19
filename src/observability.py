from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings

logger = logging.getLogger("agent_platform")


@dataclass
class MetricsRegistry:
    requests_total: Counter[str] = field(default_factory=Counter)
    request_duration_ms_total: Counter[str] = field(default_factory=Counter)
    runs_total: Counter[str] = field(default_factory=Counter)
    _lock: Lock = field(default_factory=Lock)

    def record(self, method: str, route: str, status: int, duration_ms: int) -> None:
        key = f"{method} {route} {status}"
        with self._lock:
            self.requests_total[key] += 1
            self.request_duration_ms_total[key] += duration_ms

    def record_run(self, status: str) -> None:
        with self._lock:
            self.runs_total[status] += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "runs": [{"status": status, "count": count} for status, count in sorted(self.runs_total.items())],
                "requests": [
                    {"key": key, "count": count, "duration_ms_total": self.request_duration_ms_total[key]}
                    for key, count in sorted(self.requests_total.items())
                ]
            }


metrics = MetricsRegistry()


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            metrics.record(request.method, request.url.path, 500, duration_ms)
            logger.exception("request_failed request_id=%s method=%s path=%s duration_ms=%s", request_id, request.method, request.url.path, duration_ms)
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        metrics.record(request.method, request.url.path, response.status_code, duration_ms)
        response.headers["X-Request-ID"] = request_id
        logger.info("request_completed request_id=%s method=%s path=%s status=%s duration_ms=%s", request_id, request.method, request.url.path, response.status_code, duration_ms)
        return response


def configure_observability(app: FastAPI) -> None:
    settings = get_settings()
    if settings.observability_enabled:
        app.add_middleware(RequestObservabilityMiddleware)
    if settings.sentry_dsn:
        try:  # Optional dependency: production only when SENTRY_DSN is configured.
            import sentry_sdk

            sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1, send_default_pii=False)
        except ImportError:
            logger.warning("SENTRY_DSN is configured but sentry-sdk is not installed")
