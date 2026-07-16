from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE, HTTP_409_CONFLICT

from app.core.config import settings

logger = logging.getLogger("app.exceptions")


class AppException(Exception):
    """Base exception for application-level errors."""

    def __init__(self, message: str, status_code: int = 400, code: str | None = None) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code or self.__class__.__name__
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, status_code=401, code="unauthorized")


class ConflictError(AppException):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message, status_code=409, code="conflict")


class ExternalServiceError(AppException):
    def __init__(self, service: str, message: str = "External service failure", status_code: int = HTTP_503_SERVICE_UNAVAILABLE) -> None:
        super().__init__(message, status_code=status_code, code="external_service_error")
        self.service = service


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: Any | None = None


def _get_request_id(request: Request | None) -> str | None:
    if not request:
        return None
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = request.headers.get(settings.REQUEST_ID_HEADER_NAME)
    return rid


def _format_response(code: str, message: str, request_id: str | None = None, details: Any | None = None) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    if request_id:
        payload["request_id"] = request_id
    if settings.DEBUG or settings.ERROR_VERBOSITY == "verbose":
        payload["details"] = details
    return payload


def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    request_id = _get_request_id(request)
    logger.warning("AppException: %s request_id=%s", exc.message, request_id)
    content = _format_response(exc.code or "error", exc.message, request_id, details=None)
    return JSONResponse(status_code=exc.status_code, content=content)


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = _get_request_id(request)
    msg = exc.detail if isinstance(exc.detail, (str,)) else str(exc.detail)
    logger.info("HTTPException: %s status=%s request_id=%s", msg, exc.status_code, request_id)
    content = _format_response("http_error", msg or "HTTP error", request_id, details=None)
    return JSONResponse(status_code=exc.status_code or 500, content=content)


def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = _get_request_id(request)
    errors = exc.errors()
    logger.debug("Validation error request_id=%s errors=%s", request_id, errors)
    content = _format_response("validation_error", "Invalid request parameters", request_id, details=errors)
    return JSONResponse(status_code=HTTP_400_BAD_REQUEST, content=content)


def db_exception_handler(request: Request | None, exc: Exception) -> JSONResponse:
    # Lazy import to avoid top-level dependency if SQLAlchemy not installed
    try:
        from sqlalchemy.exc import IntegrityError, OperationalError
    except Exception:  # pragma: no cover - environment dependent
        IntegrityError = OperationalError = Exception

    request_id = _get_request_id(request) if request is not None else None
    if isinstance(exc, IntegrityError):
        logger.warning("DB IntegrityError request_id=%s detail=%s", request_id, str(exc))
        content = _format_response("db_conflict", "Conflict writing to database", request_id, details=None)
        return JSONResponse(status_code=HTTP_409_CONFLICT, content=content)
    if isinstance(exc, OperationalError):
        logger.error("DB OperationalError request_id=%s detail=%s", request_id, str(exc))
        content = _format_response("db_unavailable", "Database unavailable", request_id, details=None)
        return JSONResponse(status_code=HTTP_503_SERVICE_UNAVAILABLE, content=content)

    # Fallback for unrecognized DB issues
    logger.exception("Unhandled DB exception request_id=%s", request_id)
    content = _format_response("db_error", "Database error", request_id, details=None)
    return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content=content)


def external_service_exception_handler(request: Request | None, exc: ExternalServiceError) -> JSONResponse:
    request_id = _get_request_id(request) if request is not None else None
    logger.warning("ExternalServiceError service=%s request_id=%s message=%s", getattr(exc, "service", None), request_id, exc.message)
    content = _format_response("external_service_error", "Upstream service error", request_id, details={"service": getattr(exc, "service", None)})
    return JSONResponse(status_code=exc.status_code or HTTP_503_SERVICE_UNAVAILABLE, content=content)


def unhandled_exception_handler(request: Request | None, exc: Exception) -> JSONResponse:
    request_id = _get_request_id(request) if request is not None else None
    # Log full traceback for observability; do not expose internals to users
    logger.exception("Unhandled exception request_id=%s: %s", request_id, exc)
    details = None
    if settings.DEBUG or settings.ERROR_VERBOSITY == "verbose":
        details = {
            "type": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
        }
    content = _format_response("internal_error", "Internal server error", request_id, details=details)
    return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content=content)

