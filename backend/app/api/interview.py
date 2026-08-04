from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.schemas.interview import InterviewCreate, InterviewResponse, InterviewUpdate
from app.services.interview_management import InterviewService

router = APIRouter(prefix="/interviews", tags=["interviews"])


def get_interview_service(db: Session = Depends(get_db)) -> InterviewService:
    return InterviewService(
        InterviewRepository(db),
        ApplicationRepository(db),
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
