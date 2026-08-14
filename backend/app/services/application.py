from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.audit import AUDIT_ACTOR_USER, AuditAction, AuditResourceType
from app.core.application_status import DEFAULT_APPLICATION_STATUS, validate_status_transition
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.application import ApplicationCreate, ApplicationCandidateSummary, ApplicationPipelineResponse
from app.schemas.candidate_portal import CandidateApplicationResponse
from app.services.audit_service import emit_audit as emit_audit_event
from app.services.notification import NotificationService
from app.services.notification_factory import build_notification_event_producer
from app.services.reporting_cache import invalidate_company_reporting_cache

APPLICATION_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class ApplicationService:
    """Service for tenant-scoped job application operations."""

    def __init__(
        self,
        application_repository: ApplicationRepository,
        job_repository: JobRepository,
        candidate_repository: CandidateRepository,
        member_repository: CompanyMemberRepository,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.application_repository = application_repository
        self.job_repository = job_repository
        self.candidate_repository = candidate_repository
        self.member_repository = member_repository
        _ = notification_service
        self.notification_events = build_notification_event_producer(application_repository.db)

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
        created = self.application_repository.create(application)
        invalidate_company_reporting_cache(job.company_id)
        return created

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
        updated = self.apply_status_transition(
            company_id=membership.company_id,
            application_id=application.id,
            new_status=new_status,
            actor_id=user.id,
            actor_type=AUDIT_ACTOR_USER,
        )
        return self._to_pipeline_response(updated)

    def apply_status_transition(
        self,
        *,
        company_id: UUID,
        application_id: UUID,
        new_status: str,
        commit: bool = True,
        emit_notifications: bool | None = None,
        emit_audit: bool | None = None,
        actor_id: UUID | None = None,
        actor_type: str = AUDIT_ACTOR_USER,
    ) -> Application:
        """Trusted tenant-scoped status transition for internal service callers.

        When ``commit`` is False (nested offer transactions), notifications and
        audit default off so the outer offer producer remains the lifecycle authority.
        """
        application = self._get_application_for_company(application_id, company_id)
        if application.status == new_status:
            return application
        previous_status = application.status
        validated_status = validate_status_transition(application.status, new_status)
        updated = self.application_repository.update(
            application,
            {
                "status": validated_status,
                "updated_at": datetime.now(timezone.utc),
            },
            commit=commit,
        )
        should_notify = emit_notifications if emit_notifications is not None else commit
        should_audit = emit_audit if emit_audit is not None else commit

        if not commit:
            if should_notify and self.notification_events is not None:
                self.notification_events.application_status_changed(
                    application=updated,
                    previous_status=previous_status,
                    new_status=str(validated_status),
                )
            return updated

        refreshed = self.application_repository.get_with_relations_for_company(updated.id, company_id)
        if refreshed is None:
            raise LookupError("Application not found")
        if should_notify and self.notification_events is not None:
            self.notification_events.application_status_changed(
                application=refreshed,
                previous_status=previous_status,
                new_status=str(validated_status),
            )
        if should_audit:
            emit_audit_event(
                self.application_repository.db,
                company_id=company_id,
                actor_type=actor_type,
                actor_id=actor_id,
                action=AuditAction.APPLICATION_STATUS_CHANGED.value,
                resource_type=AuditResourceType.APPLICATION.value,
                resource_id=refreshed.id,
                metadata={
                    "previous_status": previous_status,
                    "new_status": str(validated_status),
                    "job_id": str(refreshed.job_id),
                    "candidate_id": str(refreshed.candidate_id),
                },
            )
        invalidate_company_reporting_cache(company_id)
        return refreshed

    def get_application_resume_path(self, user: User, application_id: UUID) -> str:
        membership = self._resolve_active_membership(user)
        application = self._get_application_for_company(application_id, membership.company_id)
        if not application.resume_path:
            raise LookupError("Resume not found for this application")
        return application.resume_path

    def _to_candidate_response(self, application: Application) -> CandidateApplicationResponse:
        job = application.job
        company = application.company
        return CandidateApplicationResponse(
            id=application.id,
            status=application.status,
            source=application.source,
            applied_at=application.applied_at,
            updated_at=application.updated_at,
            job_id=application.job_id,
            job_title=job.title if job is not None else None,
            company_id=application.company_id,
            company_name=company.name if company is not None else None,
        )

    def list_applications_for_authenticated_candidate(
        self,
        candidate: Candidate,
    ) -> list[CandidateApplicationResponse]:
        applications = self.application_repository.list_owned_by_candidate(candidate.id)
        return [self._to_candidate_response(item) for item in applications]

    def get_application_for_authenticated_candidate(
        self,
        candidate: Candidate,
        application_id: UUID,
    ) -> CandidateApplicationResponse:
        application = self.application_repository.get_owned_by_candidate(application_id, candidate.id)
        if application is None:
            raise LookupError("Application not found")
        return self._to_candidate_response(application)
