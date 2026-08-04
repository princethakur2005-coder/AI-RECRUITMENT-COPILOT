from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.company_member import CompanyMember
from app.models.job import Job
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.job import JobRepository
from app.schemas.job import JobCreate, JobUpdate
from app.services.base import BaseService
from app.services.job_intelligence_engine import JobIntelligenceEngine

JOB_ALLOWED_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})


class JobService(BaseService[Job]):
    """Service layer for tenant-scoped job operations."""

    def __init__(
        self,
        repository: JobRepository,
        member_repository: CompanyMemberRepository,
        branch_repository: BranchRepository,
        intelligence_engine: JobIntelligenceEngine | None = None,
    ) -> None:
        super().__init__(repository)
        self.member_repository = member_repository
        self.branch_repository = branch_repository
        self.intelligence_engine = intelligence_engine or JobIntelligenceEngine()

    def _resolve_active_membership(self, user: User) -> CompanyMember:
        membership = self.member_repository.get_by_user_id(user.id)
        if not membership or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in JOB_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for job management")
        return membership

    def _validate_branch_for_company(self, company_id: UUID, branch_id: UUID) -> None:
        branch = self.branch_repository.get_by_id(branch_id)
        if not branch or branch.company_id != company_id:
            raise LookupError("Branch not found for this company")

    def _resolve_branch_id(self, company_id: UUID, branch_id: UUID | None) -> UUID | None:
        if branch_id is None:
            return None
        self._validate_branch_for_company(company_id, branch_id)
        return branch_id

    def _get_job_for_membership(self, job_id: UUID, membership: CompanyMember) -> Job:
        job = self.repository.get_by_id_for_company(job_id, membership.company_id)
        if not job:
            raise LookupError("Job not found")
        return job

    def create_job(self, user: User, payload: JobCreate) -> Job:
        membership = self._resolve_active_membership(user)
        branch_id = self._resolve_branch_id(membership.company_id, payload.branch_id)

        job = Job(
            company_id=membership.company_id,
            company_member_id=membership.id,
            branch_id=branch_id,
            created_by_id=user.id,
            title=payload.title,
            description=payload.description,
            department=payload.department,
            location=payload.location,
            employment_type=payload.employment_type,
            experience_level=payload.experience_level,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            salary_currency=payload.salary_currency,
            openings=payload.openings,
            status=payload.status,
            is_active=payload.is_active,
        )
        created = self.repository.create(job)
        return self.refresh_job_intelligence(created)

    def list_jobs(self, user: User) -> list[Job]:
        membership = self._resolve_active_membership(user)
        return self.repository.list_by_company_id(membership.company_id)

    def get_job(self, user: User, job_id: UUID) -> Job:
        membership = self._resolve_active_membership(user)
        return self._get_job_for_membership(job_id, membership)

    def update_job(self, user: User, job_id: UUID, payload: JobUpdate) -> Job:
        membership = self._resolve_active_membership(user)
        job = self._get_job_for_membership(job_id, membership)

        update_data = payload.model_dump(exclude_unset=True)
        if "branch_id" in update_data:
            update_data["branch_id"] = self._resolve_branch_id(
                membership.company_id,
                update_data["branch_id"],
            )

        updated = self.repository.update(job, update_data)
        if (
            "description" in update_data
            or "title" in update_data
            or not updated.job_intelligence
        ):
            return self.refresh_job_intelligence(updated)
        return updated

    def delete_job(self, user: User, job_id: UUID) -> None:
        membership = self._resolve_active_membership(user)
        job = self._get_job_for_membership(job_id, membership)
        self.repository.delete(job)

    def get_active_jobs(self, company_id: UUID) -> list[Job]:
        return self.repository.get_active_jobs(company_id)

    def get_jobs_by_department(self, company_id: UUID, department: str) -> list[Job]:
        return self.repository.get_by_department(company_id, department)

    def search_jobs(self, company_id: UUID, query: str) -> list[Job]:
        return self.repository.search_jobs(company_id, query)

    def refresh_job_intelligence(self, job: Job) -> Job:
        intelligence = self.intelligence_engine.build_intelligence(
            job_description=job.description or "",
            title=job.title,
        )
        return self.repository.set_job_intelligence(job, intelligence)

    def update(self, db_obj: Job, obj_in: dict[str, Any]) -> Job:
        updated = self.repository.update(db_obj, obj_in)
        if "description" in obj_in or "title" in obj_in or not updated.job_intelligence:
            return self.refresh_job_intelligence(updated)
        return updated
