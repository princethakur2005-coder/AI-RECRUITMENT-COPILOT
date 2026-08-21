from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core import config as app_config
from app.core.monitoring import (
    dependency_health_report,
    liveness_report,
    readiness_http_status,
    readiness_report,
)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    settings = app_config.get_settings()
    report = readiness_report()
    status_code = readiness_http_status(report)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "unhealthy",
            "service": settings.PROJECT_NAME,
            "ready": report.get("status"),
        },
    )


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    return liveness_report()


@router.get("/health/ready")
async def health_ready() -> JSONResponse:
    report = readiness_report()
    return JSONResponse(status_code=readiness_http_status(report), content=report)


@router.get("/health/dependencies", response_model=None)
async def health_dependencies() -> dict:
    if not app_config.get_settings().DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    return dependency_health_report()
