from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.application_ai_analysis import ApplicationAIAnalysisRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_ai_analysis import InterviewAIAnalysisRepository
from app.repositories.notification import NotificationRepository
from app.schemas.interview import InterviewCreate, InterviewResponse, InterviewUpdate
from app.schemas.interview_ai_analysis import InterviewAIAnalysisResponse
from app.services.interview_intelligence import InterviewIntelligenceService
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService

router = APIRouter(prefix="/interviews", tags=["interviews"])


def get_interview_service(db: Session = Depends(get_db)) -> InterviewService:
    return InterviewService(
        InterviewRepository(db),
        ApplicationRepository(db),
        CompanyMemberRepository(db),
        notification_service=NotificationService(
            NotificationRepository(db),
            CompanyMemberRepository(db),
        ),
    )


def get_interview_intelligence_service(db: Session = Depends(get_db)) -> InterviewIntelligenceService:
    return InterviewIntelligenceService(
        InterviewRepository(db),
        InterviewAIAnalysisRepository(db),
        ApplicationRepository(db),
        ApplicationAIAnalysisRepository(db),
        CompanyMemberRepository(db),
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


@router.post("", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
def create_interview(
    payload: InterviewCreate,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewResponse:
    try:
        return service.create_interview(current_user, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("", response_model=list[InterviewResponse])
def list_interviews(
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> list[InterviewResponse]:
    try:
        return service.list_interviews(current_user)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/{interview_id}/ai", response_model=InterviewAIAnalysisResponse)
def get_interview_ai_analysis(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    service: InterviewIntelligenceService = Depends(get_interview_intelligence_service),
) -> InterviewAIAnalysisResponse:
    try:
        return service.get_analysis(current_user, interview_id)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.post("/{interview_id}/ai/analyze", response_model=InterviewAIAnalysisResponse)
def analyze_interview_intelligence(
    interview_id: UUID,
    force: bool = Query(default=False, description="Regenerate analysis even if one exists"),
    current_user: User = Depends(get_current_user),
    service: InterviewIntelligenceService = Depends(get_interview_intelligence_service),
) -> InterviewAIAnalysisResponse:
    try:
        return service.analyze_interview(current_user, interview_id, force=force)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.get("/{interview_id}", response_model=InterviewResponse)
def get_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewResponse:
    try:
        return service.get_interview(current_user, interview_id)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.patch("/{interview_id}", response_model=InterviewResponse)
def update_interview(
    interview_id: UUID,
    payload: InterviewUpdate,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewResponse:
    try:
        return service.update_interview(current_user, interview_id, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> None:
    try:
        service.delete_interview(current_user, interview_id)
    except Exception as exc:  # noqa: BLE001
        _handle_service_errors(exc)
        raise
