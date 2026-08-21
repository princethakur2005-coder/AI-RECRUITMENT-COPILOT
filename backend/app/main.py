from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.application import router as application_router
from app.api.audit import router as audit_router
from app.api.public_apply import router as public_apply_router
from app.api.auth import router as auth_router
from app.api.assistant import router as assistant_router
from app.api.candidate import router as candidate_router
from app.api.candidate_portal import router as candidate_portal_router
from app.api.branch import router as branch_router
from app.api.company import router as company_router
from app.api.company_member import router as company_member_router
from app.api.dashboard import router as dashboard_router
from app.api.interview import router as interview_router
from app.api.job import router as job_router
from app.api.note import router as note_router
from app.api.notification import router as notification_router
from app.api.offer import router as offer_router
from app.api.search import router as search_router
from app.api.user import router as user_router
from app.api.webhook import router as webhook_router
from app.api.calendar import router as calendar_router
from app.api.health import router as health_router
from app.api.workspace import router as workspace_router
from app.core.config import get_settings, settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.security import RequestSizeLimiterMiddleware, SecurityHardeningMiddleware
from app.middleware.error import RequestCorrelationMiddleware, GracefulDegradationMiddleware
from app.core.exceptions import (
    ExternalServiceError,
    db_exception_handler,
    external_service_exception_handler,
    unhandled_exception_handler as core_unhandled_exception,
)
from app.core.runtime_validation import validate_api_runtime
from app.middleware.request_logging import request_logging_middleware
from app.middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware, RequestValidationMiddleware
from app.middleware.performance import (
    RequestTimingMiddleware,
    CacheControlMiddleware,
    ResponseCompressionMiddleware,
)
from fastapi.exceptions import RequestValidationError

configure_logging()

# Import all models so Base.metadata is fully populated before create_all
import app.models  # noqa: F401, E402

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(RequestCorrelationMiddleware)
app.add_middleware(RequestSizeLimiterMiddleware, max_body_size=settings.MAX_REQUEST_SIZE)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SecurityHardeningMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(GracefulDegradationMiddleware)
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(CacheControlMiddleware)
app.add_middleware(ResponseCompressionMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
    max_age=600,
)

app.middleware("http")(request_logging_middleware)
app.include_router(auth_router)
app.include_router(public_apply_router)
app.include_router(company_router)
app.include_router(branch_router)
app.include_router(company_member_router)
app.include_router(candidate_router)
app.include_router(candidate_portal_router)
app.include_router(job_router)
app.include_router(application_router)
app.include_router(interview_router)
app.include_router(note_router)
app.include_router(notification_router)
app.include_router(offer_router)
app.include_router(webhook_router)
app.include_router(calendar_router)
app.include_router(assistant_router)
app.include_router(user_router)
app.include_router(dashboard_router)
app.include_router(audit_router)
app.include_router(search_router)
app.include_router(workspace_router)
app.include_router(health_router)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
# Register DB handler if SQLAlchemy is present
try:
    from sqlalchemy.exc import SQLAlchemyError  # type: ignore

    app.add_exception_handler(SQLAlchemyError, db_exception_handler)
except Exception:
    # SQLAlchemy not available in this environment; skip registration
    pass

# External service errors
app.add_exception_handler(ExternalServiceError, external_service_exception_handler)

# Fallback handler for everything else
app.add_exception_handler(Exception, core_unhandled_exception)
app.add_exception_handler(404, http_exception_handler)


@app.on_event("startup")
def on_startup() -> None:
    """Validate runtime configuration and optionally bootstrap dev tables."""
    runtime_settings = get_settings()
    validate_api_runtime(runtime_settings)
    if not runtime_settings.DEBUG:
        return
    from app.db.base import Base
    from app.db.database import engine

    Base.metadata.create_all(bind=engine)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "running",
        "message": settings.PROJECT_NAME,
    }
