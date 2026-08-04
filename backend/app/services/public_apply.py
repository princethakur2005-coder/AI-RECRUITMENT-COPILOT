from __future__ import annotations

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.application_source import APPLICATION_SOURCE_CAREERS_PAGE
from app.core.application_status import DEFAULT_APPLICATION_STATUS
from app.models.application import Application
from app.models.candidate import Candidate
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.schemas.public_apply import PublicApplyForm, PublicApplyResponse
from app.utils.resume_management import ResumeManager


class DuplicateApplicationError(ValueError):
    """Raised when a candidate has already applied to the job."""


class PublicApplyService:
    """Orchestrates public job applications with resume upload and tenant scoping."""

    def __init__(
        self,
        db: Session,
        job_repository: JobRepository,
        candidate_repository: CandidateRepository,
        application_repository: ApplicationRepository,
        resume_manager: ResumeManager | None = None,
    ) -> None:
        self.db = db
        self.job_repository = job_repository
        self.candidate_repository = candidate_repository
        self.application_repository = application_repository
        self.resume_manager = resume_manager or ResumeManager()

    def submit_application(
        self,
        job_id: UUID,
        form: PublicApplyForm,
        resume_file: UploadFile,
    ) -> PublicApplyResponse:
        job = self.job_repository.get_job_for_public_apply(job_id)
        if not job:
            raise LookupError("Job not found or is not open for applications")

        company_id = job.company_id
        resume_path: str | None = None

        try:
            upload_result = self.resume_manager.upload_resume(resume_file)
            resume_path = upload_result["path"]
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        try:
            application = self._create_application_transaction(
                company_id=company_id,
                job_id=job.id,
                form=form,
                resume_path=resume_path,
            )
        except Exception:
            if resume_path:
                self.resume_manager.delete_resume(resume_path)
            raise

        return PublicApplyResponse(
            application_id=application.id,
            job_id=application.job_id,
            candidate_id=application.candidate_id,
            status=application.status,
            applied_at=application.applied_at,
        )

    def _create_application_transaction(
        self,
        company_id: UUID,
        job_id: UUID,
        form: PublicApplyForm,
        resume_path: str,
    ) -> Application:
        email = str(form.email).strip()
        full_name = " ".join(form.full_name.split()).strip()
        first_name, last_name = self._split_name(full_name)

        try:
            candidate = self.candidate_repository.get_by_email(email)
            if candidate is None:
                candidate = Candidate(
                    first_name=first_name or "Candidate",
                    last_name=last_name or "",
                    full_name=full_name or email,
                    email=email,
                    phone=form.phone,
                    resume_path=resume_path,
                    status="new",
                    is_active=True,
                )
                self.db.add(candidate)
            else:
                candidate.full_name = full_name or candidate.full_name
                candidate.first_name = first_name or candidate.first_name
                candidate.last_name = last_name or candidate.last_name
                if form.phone:
                    candidate.phone = form.phone
                candidate.resume_path = resume_path
                self.db.add(candidate)

            self.db.flush()

            if self.application_repository.get_by_candidate_and_job(candidate.id, job_id):
                raise DuplicateApplicationError("You have already applied to this job")

            application = Application(
                company_id=company_id,
                job_id=job_id,
                candidate_id=candidate.id,
                resume_path=resume_path,
                status=DEFAULT_APPLICATION_STATUS,
                source=APPLICATION_SOURCE_CAREERS_PAGE,
            )
            self.db.add(application)
            self.db.commit()
            self.db.refresh(application)
            return application
        except DuplicateApplicationError:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_applications_candidate_job" in str(exc.orig):
                raise DuplicateApplicationError("You have already applied to this job") from exc
            if "email" in str(exc.orig).lower() or "ix_candidates_email" in str(exc.orig):
                raise ValueError("Unable to process application for this email address") from exc
            raise
        except Exception:
            self.db.rollback()
            raise

    def _split_name(self, full_name: str) -> tuple[str, str]:
        parts = full_name.split()
        if not parts:
            return "Candidate", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])
