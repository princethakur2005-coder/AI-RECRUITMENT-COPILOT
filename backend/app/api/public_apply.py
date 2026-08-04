from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.schemas.public_apply import PublicApplyForm, PublicApplyResponse
from app.services.public_apply import DuplicateApplicationError, PublicApplyService
from app.utils.resume_management import ResumeManager

router = APIRouter(prefix="/public/jobs", tags=["public-apply"])


def get_public_apply_service(db: Session = Depends(get_db)) -> PublicApplyService:
    return PublicApplyService(
        db,
        JobRepository(db),
        CandidateRepository(db),
        ApplicationRepository(db),
        ResumeManager(),
    )


@router.post("/{job_id}/apply", response_model=PublicApplyResponse, status_code=status.HTTP_201_CREATED)
def submit_public_application(
    job_id: UUID,
    email: str = Form(...),
    full_name: str = Form(...),
    phone: str | None = Form(default=None),
    resume: UploadFile = File(...),
    service: PublicApplyService = Depends(get_public_apply_service),
) -> PublicApplyResponse:
    try:
        form = PublicApplyForm(email=email, full_name=full_name, phone=phone)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.errors(),
        ) from exc

    try:
        return service.submit_application(job_id, form, resume)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DuplicateApplicationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to submit application",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to submit application",
        ) from exc
