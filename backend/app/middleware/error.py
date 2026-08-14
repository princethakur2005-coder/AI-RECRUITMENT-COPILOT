from __future__ import annotations

import uuid
import logging
from typing import Any, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.logging import request_id_context, set_request_id

logger = logging.getLogger("app.middleware.error")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Attach or generate a correlation id for each request and expose it on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        header_name = settings.REQUEST_ID_HEADER_NAME
        request_id = request.headers.get(header_name) or str(uuid.uuid4())
        request.state.request_id = request_id
        set_request_id(request_id)
        response = await call_next(request)
        if header_name not in response.headers:
            response.headers[header_name] = request_id
        return response


class GracefulDegradationMiddleware(BaseHTTPMiddleware):
    """Placeholder middleware to enable graceful degradation for external failures.

    This middleware currently re-raises exceptions and can be extended to return cached
    or degraded responses based on configuration.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.debug("GracefulDegradationMiddleware caught exception: %s", exc)
            if settings.RESILIENCE_GRACEFUL_DEGRADATION_ENABLED:
                # Return a minimal degraded response for non-critical endpoints.
                # Real implementations would inspect the exception type and route metadata.
                return Response(status_code=503, content=b"Service temporarily unavailable")
            raise
