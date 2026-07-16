from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import logger, request_id_context
from app.core.monitoring import metrics_registry


async def request_logging_middleware(request: Request, call_next: Callable[[Request], Response]) -> Response:
    start_time = time.perf_counter()
    request_id = request.headers.get(settings.REQUEST_ID_HEADER_NAME, str(uuid.uuid4()))
    request.state.request_id = request_id
    token = request_id_context.set(request_id)

    logger.info(
        "request_started",
        extra={
            "event": "request_started",
            "method": request.method,
            "path": request.url.path,
        },
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        metrics_registry.observe_error(path=request.url.path, error_type=exc.__class__.__name__)
        metrics_registry.observe_http_request(
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
        )
        logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "error_type": exc.__class__.__name__,
            },
        )
        request_id_context.reset(token)
        raise

    response.headers[settings.REQUEST_ID_HEADER_NAME] = request_id

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    metrics_registry.observe_http_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    logger.info(
        "request_completed",
        extra={
            "event": "request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    request_id_context.reset(token)
    return response
