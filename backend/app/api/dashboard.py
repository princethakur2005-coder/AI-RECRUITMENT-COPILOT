from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_hiring_decision import ApplicationHiringDecisionRepository
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.repositories.offer import OfferRepository
from app.repositories.reporting import ReportingRepository
from app.schemas.candidate_ranking import TopCandidatesResponse
from app.schemas.recruiter_dashboard import (
    DashboardJobListResponse,
    DashboardOverviewResponse,
    DashboardPipelineResponse,
    DashboardRecentApplicationsResponse,
    DashboardStatsResponse,
    DashboardUpcomingInterviewsResponse,
)
from app.schemas.recruiter_workspace import RecruiterWorkspaceResponse
from app.schemas.reporting import (
    ReportingOverviewResponse,
    ReportingPipelineResponse,
    ReportingTimeSeriesResponse,
)
from app.services.dashboard_service import DashboardService
from app.services.recruiter_dashboard import DASHBOARD_ALLOWED_ROLES, RecruiterDashboardService
from app.services.candidate_ranking import CandidateRankingService
from app.services.recruiter_workspace import RecruiterWorkspaceService
from app.services.reporting import ReportingService

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


def get_candidate_ranking_service(db: Session = Depends(get_db)) -> CandidateRankingService:
    return CandidateRankingService(
        ApplicationRepository(db),
        JobRepository(db),
        CompanyMemberRepository(db),
    )


def get_recruiter_workspace_service(db: Session = Depends(get_db)) -> RecruiterWorkspaceService:
    return RecruiterWorkspaceService(
        db=db,
        application_repository=ApplicationRepository(db),
        hiring_decision_repository=ApplicationHiringDecisionRepository(db),
        offer_repository=OfferRepository(db),
        member_repository=CompanyMemberRepository(db),
    )


def get_reporting_service(db: Session = Depends(get_db)) -> ReportingService:
    return ReportingService(
        ReportingRepository(db),
        CompanyMemberRepository(db),
        JobRepository(db),
        BranchRepository(db),
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


def get_dashboard_member_user(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Staff dashboard routes require active company membership and dashboard RBAC."""
    membership = CompanyMemberRepository(db).get_by_user_id(user.id)
    if membership is None or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active company membership required",
        )
    if membership.role not in DASHBOARD_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for recruiter dashboard",
        )
    return user


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


@router.get("/top-candidates", response_model=TopCandidatesResponse)
def recruiter_dashboard_top_candidates(
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    service: CandidateRankingService = Depends(get_candidate_ranking_service),
) -> TopCandidatesResponse:
    try:
        return service.get_top_candidates(user, limit=limit)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/workspace", response_model=RecruiterWorkspaceResponse)
def recruiter_workspace(
    user: User = Depends(get_current_user),
    service: RecruiterWorkspaceService = Depends(get_recruiter_workspace_service),
) -> RecruiterWorkspaceResponse:
    try:
        return service.get_workspace_for_user(user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/analytics/overview", response_model=ReportingOverviewResponse)
def reporting_overview(
    branch_id: UUID | None = Query(None),
    job_id: UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: User = Depends(get_current_user),
    service: ReportingService = Depends(get_reporting_service),
) -> ReportingOverviewResponse:
    try:
        return service.get_overview(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/analytics/pipeline", response_model=ReportingPipelineResponse)
def reporting_pipeline(
    branch_id: UUID | None = Query(None),
    job_id: UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: User = Depends(get_current_user),
    service: ReportingService = Depends(get_reporting_service),
) -> ReportingPipelineResponse:
    try:
        return service.get_pipeline(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/analytics/time-series", response_model=ReportingTimeSeriesResponse)
def reporting_time_series(
    branch_id: UUID | None = Query(None),
    job_id: UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: User = Depends(get_current_user),
    service: ReportingService = Depends(get_reporting_service),
) -> ReportingTimeSeriesResponse:
    try:
        return service.get_time_series(
            user,
            branch_id=branch_id,
            job_id=job_id,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/summary")
def dashboard_summary(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
    return service.get_dashboard()


@router.get("/pipeline-metrics")
def pipeline_metrics(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
    return service.get_pipeline_widget()


@router.get("/funnel")
def funnel_metrics(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
    return service.get_funnel_widget()


@router.get("/job-metrics")
def job_statistics(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
    return service.get_job_statistics_widget()


@router.get("/interviews")
def interview_metrics(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
    return service.get_interview_metrics_widget()


@router.get("/activities")
def recent_activity(
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
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
    user: User = Depends(get_dashboard_member_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    _ = user
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
