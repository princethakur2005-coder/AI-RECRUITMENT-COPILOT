from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.application_status import DEFAULT_APPLICATION_STATUS, validate_status_transition
from app.models.application import Application
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationCreate, ApplicationCandidateSummary, ApplicationPipelineResponse

APPLICATION_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class ApplicationService:
    """Service for tenant-scoped job application operations."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        job_repository: JobRepository,
        candidate_repository: CandidateRepository,
        member_repository: CompanyMemberRepository,
    ) -> None:
        self.application_repository = application_repository
        self.job_repository = job_repository
        self.candidate_repository = candidate_repository
        self.member_repository = member_repository

    def _resolve_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in APPLICATION_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for application management")
        return membership

    def _get_application_for_company(self, application_id: UUID, company_id: UUID) -> Application:
        application = self.application_repository.get_by_id_for_company(application_id, company_id)
        if not application:
            raise LookupError("Application not found")
        return application

    def _to_pipeline_response(self, application: Application) -> ApplicationPipelineResponse:
        candidate = application.candidate
        candidate_summary = None
        if candidate is not None:
            candidate_summary = ApplicationCandidateSummary(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
            )
        return ApplicationPipelineResponse(
            id=application.id,
            company_id=application.company_id,
            job_id=application.job_id,
            candidate_id=application.candidate_id,
            resume_path=application.resume_path,
            status=application.status,
            source=application.source,
            applied_at=application.applied_at,
            updated_at=application.updated_at,
            candidate=candidate_summary,
        )

    def create_application(self, user: User, payload: ApplicationCreate) -> Application:
        membership = self._resolve_active_membership(user)

        job = self.job_repository.get_by_id_for_company(payload.job_id, membership.company_id)
        if not job:
            raise LookupError("Job not found")

        candidate = self.candidate_repository.get_by_id(payload.candidate_id)
        if not candidate:
            raise LookupError("Candidate not found")

        if self.application_repository.get_by_candidate_and_job(payload.candidate_id, payload.job_id):
            raise ValueError("Candidate has already applied to this job")

        application = Application(
            company_id=job.company_id,
            job_id=job.id,
            candidate_id=candidate.id,
            resume_path=payload.resume_path,
            status=DEFAULT_APPLICATION_STATUS,
            source=payload.source,
        )
        return self.application_repository.create(application)

    def list_applications(self, user: User) -> list[ApplicationPipelineResponse]:
        membership = self._resolve_active_membership(user)
        applications = self.application_repository.list_by_company_id(membership.company_id)
        return [self._to_pipeline_response(item) for item in applications]

    def get_application(self, user: User, application_id: UUID) -> ApplicationPipelineResponse:
        membership = self._resolve_active_membership(user)
        application = self._get_application_for_company(application_id, membership.company_id)
        return self._to_pipeline_response(application)

    def list_applications_for_job(self, user: User, job_id: UUID) -> list[ApplicationPipelineResponse]:
        membership = self._resolve_active_membership(user)
        job = self.job_repository.get_by_id_for_company(job_id, membership.company_id)
        if not job:
            raise LookupError("Job not found")
        applications = self.application_repository.list_by_job_id(membership.company_id, job_id)
        return [self._to_pipeline_response(item) for item in applications]

    def list_applications_for_candidate(self, user: User, candidate_id: UUID) -> list[ApplicationPipelineResponse]:
        membership = self._resolve_active_membership(user)
        candidate = self.candidate_repository.get_by_id(candidate_id)
        if not candidate:
            raise LookupError("Candidate not found")
        applications = self.application_repository.list_by_candidate_id(membership.company_id, candidate_id)
        return [self._to_pipeline_response(item) for item in applications]

    def update_application_status(
        self,
        user: User,
        application_id: UUID,
        new_status: str,
    ) -> ApplicationPipelineResponse:
        membership = self._resolve_active_membership(user)
        application = self._get_application_for_company(application_id, membership.company_id)
        validated_status = validate_status_transition(application.status, new_status)
        updated = self.application_repository.update(
            application,
            {
                "status": validated_status,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        refreshed = self.application_repository.get_by_id_for_company(updated.id, membership.company_id)
        if refreshed is None:
            raise LookupError("Application not found")
        return self._to_pipeline_response(refreshed)

    def get_application_resume_path(self, user: User, application_id: UUID) -> str:
        membership = self._resolve_active_membership(user)
        application = self._get_application_for_company(application_id, membership.company_id)
        if not application.resume_path:
            raise LookupError("Resume not found for this application")
        return application.resume_path
