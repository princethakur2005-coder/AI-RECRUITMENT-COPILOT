from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.services.job import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(db: Session = Depends(get_db)) -> JobService:
    repository = JobRepository(db)
    return JobService(repository)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    service: JobService = Depends(get_job_service),
) -> Job:
    job = Job(**payload.model_dump())
    return service.create_job(job)


@router.get("", response_model=list[JobResponse])
def list_jobs(
    service: JobService = Depends(get_job_service),
) -> list[Job]:
    return service.get_all()


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> Job:
    job = service.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    payload: JobUpdate,
    service: JobService = Depends(get_job_service),
) -> Job:
    job = service.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True)
    return service.update(job, update_data)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> None:
    job = service.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    service.delete(job)
