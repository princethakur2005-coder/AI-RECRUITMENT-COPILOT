from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.application import Application
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.schemas.application import (
    ApplicationCreate,
    ApplicationPipelineResponse,
    ApplicationStatusUpdate,
)
from app.schemas.interview import InterviewResponse
from app.services.application import ApplicationService
from app.services.interview_management import InterviewService

router = APIRouter(prefix="/applications", tags=["applications"])


def get_application_service(db: Session = Depends(get_db)) -> ApplicationService:
    return ApplicationService(
        ApplicationRepository(db),
        JobRepository(db),
        CandidateRepository(db),
        CompanyMemberRepository(db),
    )


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


@router.post("", response_model=ApplicationPipelineResponse, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        application = service.create_application(current_user, payload)
        return service.get_application(current_user, application.id)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        _handle_service_errors(exc)
        raise


@router.get("", response_model=list[ApplicationPipelineResponse])
def list_applications(
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications(current_user)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/candidate/{candidate_id}", response_model=list[ApplicationPipelineResponse])
def list_candidate_applications(
    candidate_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications_for_candidate(current_user, candidate_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/job/{job_id}", response_model=list[ApplicationPipelineResponse])
def list_job_applications_legacy(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return service.list_applications_for_job(current_user, job_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.patch("/{application_id}/status", response_model=ApplicationPipelineResponse)
def update_application_status(
    application_id: UUID,
    payload: ApplicationStatusUpdate,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        return service.update_application_status(
            current_user,
            application_id,
            payload.status,
        )
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/interviews", response_model=list[InterviewResponse])
def list_application_interviews(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: InterviewService = Depends(get_interview_service),
) -> list[InterviewResponse]:
    try:
        return service.list_interviews_for_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise


@router.get("/{application_id}/resume")
def download_application_resume(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> FileResponse:
    try:
        resume_path = service.get_application_resume_path(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise

    path = Path(resume_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume file not found",
        )
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )


@router.get("/{application_id}", response_model=ApplicationPipelineResponse)
def get_application(
    application_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationPipelineResponse:
    try:
        return service.get_application(current_user, application_id)
    except Exception as exc:
        _handle_service_errors(exc)
        raise
