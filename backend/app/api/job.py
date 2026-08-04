from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.application import get_application_service
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.job import Job
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationPipelineResponse
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.services.application import ApplicationService
from app.services.job import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    return JobService(
        JobRepository(db),
        CompanyMemberRepository(db),
        BranchRepository(db),
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.create_job(current_user, payload)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("", response_model=list[JobResponse])
def list_jobs(
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> list[Job]:
    try:
        return service.list_jobs(current_user)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}/applications", response_model=list[ApplicationPipelineResponse])
def list_job_applications(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    application_service: ApplicationService = Depends(get_application_service),
) -> list[ApplicationPipelineResponse]:
    try:
        return application_service.list_applications_for_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.get_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    payload: JobUpdate,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return service.update_job(current_user, job_id, payload)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
) -> None:
    try:
        service.delete_job(current_user, job_id)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
