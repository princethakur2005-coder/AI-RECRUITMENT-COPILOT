from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.schemas.recruiter_dashboard import (
    DashboardJobListResponse,
    DashboardOverviewResponse,
    DashboardPipelineResponse,
    DashboardRecentApplicationsResponse,
    DashboardStatsResponse,
    DashboardUpcomingInterviewsResponse,
)
from app.services.dashboard_service import DashboardService
from app.services.recruiter_dashboard import RecruiterDashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return DashboardService(db=db)


def get_recruiter_dashboard_service(db: Session = Depends(get_db)) -> RecruiterDashboardService:
    return RecruiterDashboardService(
        JobRepository(db),
        ApplicationRepository(db),
        CompanyMemberRepository(db),
        InterviewRepository(db),
    )


def _handle_service_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    raise exc


@router.get("", response_model=DashboardOverviewResponse)
def recruiter_dashboard_overview(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardOverviewResponse:
    try:
        return service.get_overview(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/stats", response_model=DashboardStatsResponse)
def recruiter_dashboard_stats(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardStatsResponse:
    try:
        return service.get_stats(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/jobs", response_model=DashboardJobListResponse)
def recruiter_dashboard_jobs(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardJobListResponse:
    try:
        return service.get_jobs(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/pipeline", response_model=DashboardPipelineResponse)
def recruiter_dashboard_pipeline(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardPipelineResponse:
    try:
        return service.get_pipeline(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/recent-applications", response_model=DashboardRecentApplicationsResponse)
def recruiter_dashboard_recent_applications(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardRecentApplicationsResponse:
    try:
        return service.get_recent_applications(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/upcoming-interviews", response_model=DashboardUpcomingInterviewsResponse)
def recruiter_dashboard_upcoming_interviews(
    user: User = Depends(get_current_user),
    service: RecruiterDashboardService = Depends(get_recruiter_dashboard_service),
) -> DashboardUpcomingInterviewsResponse:
    try:
        return service.get_upcoming_interviews(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/summary")
def dashboard_summary(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_dashboard()


@router.get("/pipeline-metrics")
def pipeline_metrics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_pipeline_widget()


@router.get("/funnel")
def funnel_metrics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_funnel_widget()


@router.get("/job-metrics")
def job_statistics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_job_statistics_widget()


@router.get("/interviews")
def interview_metrics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_interview_metrics_widget()


@router.get("/activities")
def recent_activity(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_activity_widget()


@router.get("/ai-activities")
def ai_activities(
    activity_type: str | None = Query(None, description="Filter by AI activity type"),
    resource_type: str | None = Query(None, description="Filter by related entity type"),
    resource_id: str | None = Query(None, description="Filter by related entity ID"),
    status: str | None = Query(None, description="Filter by activity status"),
    sort_by: str = Query("timestamp", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    return service.get_ai_activity_events(
        activity_type=activity_type,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
