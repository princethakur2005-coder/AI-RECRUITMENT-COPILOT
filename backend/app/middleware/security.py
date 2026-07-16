from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, status
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple IP-based rate limiting for production and development."""

    def __init__(self, app: Callable) -> None:
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self.limit = settings.RATE_LIMIT_REQUESTS
        self.window = settings.RATE_LIMIT_WINDOW_SECONDS

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = self._get_client_ip(request)
        now = time.time()
        bucket = self._requests[client_ip]

        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()

        if len(bucket) >= self.limit:
            retry_after = int(bucket[0] + self.window - now) if bucket else self.window
            return JSONResponse(
                {"detail": "Rate limit exceeded. Try again later."},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        bucket.append(now)
        response = await call_next(request)
        remaining = max(0, self.limit - len(bucket))
        response.headers.setdefault("X-RateLimit-Limit", str(self.limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(remaining))
        return response

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforce a minimal set of production security headers."""

    def __init__(self, app: Callable) -> None:
        super().__init__(app)
        self.headers = {
            "X-Content-Type-Options": settings.X_CONTENT_TYPE_OPTIONS,
            "X-Frame-Options": settings.X_FRAME_OPTIONS,
            "X-XSS-Protection": settings.X_XSS_PROTECTION,
            "Referrer-Policy": settings.REFERRER_POLICY,
            "Permissions-Policy": settings.PERMISSIONS_POLICY,
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Embedder-Policy": "require-corp",
        }
        if settings.CSP_ENABLED:
            self.headers["Content-Security-Policy"] = settings.CONTENT_SECURITY_POLICY
        if settings.HSTS_ENABLED and settings.is_production:
            self.headers["Strict-Transport-Security"] = settings.STRICT_TRANSPORT_SECURITY

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in self.headers.items():
            if name not in response.headers:
                response.headers[name] = value
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Basic request validation middleware for content type and size."""

    def __init__(self, app: Callable) -> None:
        super().__init__(app)
        self.max_size = settings.MAX_REQUEST_SIZE

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            content_type = request.headers.get("content-type", "").lower()
            if content_type and not any(
                allowed in content_type
                for allowed in ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"]
            ):
                return JSONResponse(
                    {"detail": "Unsupported content type. Use application/json or multipart/form-data."},
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                )

            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_size:
                        return JSONResponse(
                            {"detail": "Request payload too large."},
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        )
                except ValueError:
                    pass

        return await call_next(request)
