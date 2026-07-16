from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.monitoring import metrics_registry

logger = logging.getLogger("app.middleware.performance")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Measure request duration, record metrics, and log slow requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000.0
        # Metrics
        try:
            metrics_registry.observe_http_request(request.method, request.url.path, response.status_code, duration)
            if duration >= settings.SLOW_REQUEST_THRESHOLD_MS:
                metrics_registry.increment("http_slow_requests_total", labels={"path": request.url.path})
                logger.warning("Slow request %s %s took %.1fms", request.method, request.url.path, duration)
        except Exception:
            logger.debug("Failed recording metrics for request timing")

        return response


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control header for safe GET requests when not provided by handlers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        try:
            if request.method == "GET" and response.status_code in (200, 203) and "cache-control" not in {k.lower() for k in response.headers}:
                ttl = settings.CACHE_CONTROL_DEFAULT_TTL
                response.headers.setdefault("Cache-Control", f"public, max-age={ttl}")
        except Exception:
            logger.debug("Failed to set Cache-Control header")
        return response


class ResponseCompressionMiddleware(GZipMiddleware):
    """Thin wrapper to allow configuration via settings."""

    def __init__(self, app: Any):
        super().__init__(app, minimum_size=settings.COMPRESS_MIN_SIZE)
