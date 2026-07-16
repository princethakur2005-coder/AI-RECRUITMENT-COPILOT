from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.candidate import get_candidate_service
from app.api.job import get_job_service
from app.db.database import get_db
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return DashboardService(db=db)


@router.get("/summary")
def dashboard_summary(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_dashboard()


@router.get("/pipeline")
def pipeline_metrics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_pipeline_widget()


@router.get("/funnel")
def funnel_metrics(service: DashboardService = Depends(get_dashboard_service)) -> dict:
    return service.get_funnel_widget()


@router.get("/jobs")
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
