from __future__ import annotations

from uuid import UUID

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.user import User
from app.repositories.branch import BranchRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.search import SearchRepository
from app.schemas.search import RecruiterSearchEntityType, RecruiterSearchHit, RecruiterSearchResponse
from app.services.recruiter_dashboard import DASHBOARD_ALLOWED_ROLES
from app.core.read_query_bounds import MAX_SEARCH_LIMIT, clamp_limit, clamp_offset

MIN_QUERY_LENGTH = 2
DEFAULT_LIMIT = 20
MAX_LIMIT = MAX_SEARCH_LIMIT

_ENTITY_ORDER = (
    RecruiterSearchEntityType.CANDIDATE,
    RecruiterSearchEntityType.JOB,
    RecruiterSearchEntityType.APPLICATION,
)


class SearchService:
    """Tenant-scoped recruiter keyword search. PostgreSQL ILIKE behind a stable API.

    Search results are intentionally uncached: query strings are high-cardinality,
    results must stay fresh after mutations, and ILIKE lookups are already bounded.
    """

    def __init__(
        self,
        search_repository: SearchRepository,
        member_repository: CompanyMemberRepository,
        branch_repository: BranchRepository,
    ) -> None:
        self.search_repository = search_repository
        self.member_repository = member_repository
        self.branch_repository = branch_repository

    def _resolve_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in DASHBOARD_ALLOWED_ROLES:
            raise PermissionError("Insufficient permissions for recruiter search")
        return membership

    def _resolve_branch(self, company_id: UUID, branch_id: UUID | None) -> UUID | None:
        if branch_id is None:
            return None
        branch = self.branch_repository.get_by_id(branch_id)
        if branch is None or branch.company_id != company_id:
            raise LookupError("Branch not found for this company")
        return branch_id

    def _empty(self, query: str, offset: int, limit: int) -> RecruiterSearchResponse:
        return RecruiterSearchResponse(query=query, offset=offset, limit=limit)

    def _candidate_hit(self, candidate: Candidate) -> RecruiterSearchHit:
        return RecruiterSearchHit(
            entity_type=RecruiterSearchEntityType.CANDIDATE,
            entity_id=candidate.id,
            title=candidate.full_name,
            subtitle=candidate.email,
            status=candidate.status,
            candidate_id=candidate.id,
        )

    def _job_hit(self, job: Job) -> RecruiterSearchHit:
        subtitle_parts = [part for part in (job.department, job.location) if part]
        return RecruiterSearchHit(
            entity_type=RecruiterSearchEntityType.JOB,
            entity_id=job.id,
            title=job.title,
            subtitle=" · ".join(subtitle_parts) or None,
            status=job.status,
            job_id=job.id,
        )

    def _application_hit(self, application: Application) -> RecruiterSearchHit:
        candidate = application.candidate
        job = application.job
        title = candidate.full_name if candidate is not None else str(application.candidate_id)
        subtitle = job.title if job is not None else None
        return RecruiterSearchHit(
            entity_type=RecruiterSearchEntityType.APPLICATION,
            entity_id=application.id,
            title=title,
            subtitle=subtitle,
            status=application.status,
            application_id=application.id,
            candidate_id=application.candidate_id,
            job_id=application.job_id,
        )

    def search(
        self,
        user: User,
        query: str,
        *,
        branch_id: UUID | None = None,
        types: set[RecruiterSearchEntityType] | None = None,
        offset: int = 0,
        limit: int = DEFAULT_LIMIT,
    ) -> RecruiterSearchResponse:
        membership = self._resolve_membership(user)
        company_id = membership.company_id
        resolved_branch = self._resolve_branch(company_id, branch_id)
        normalized = (query or "").strip()
        offset = clamp_offset(offset)
        limit = clamp_limit(limit, maximum=MAX_LIMIT)
        requested = types or set(_ENTITY_ORDER)

        if len(normalized) < MIN_QUERY_LENGTH:
            return self._empty(normalized, offset, limit)

        include_candidates = RecruiterSearchEntityType.CANDIDATE in requested
        include_jobs = RecruiterSearchEntityType.JOB in requested
        include_applications = RecruiterSearchEntityType.APPLICATION in requested

        candidate_total = (
            self.search_repository.count_candidates(company_id, normalized, branch_id=resolved_branch)
            if include_candidates
            else 0
        )
        job_total = (
            self.search_repository.count_jobs(company_id, normalized, branch_id=resolved_branch)
            if include_jobs
            else 0
        )
        application_total = (
            self.search_repository.count_applications(company_id, normalized, branch_id=resolved_branch)
            if include_applications
            else 0
        )

        segments: list[tuple[RecruiterSearchEntityType, int]] = []
        if include_candidates:
            segments.append((RecruiterSearchEntityType.CANDIDATE, candidate_total))
        if include_jobs:
            segments.append((RecruiterSearchEntityType.JOB, job_total))
        if include_applications:
            segments.append((RecruiterSearchEntityType.APPLICATION, application_total))

        items: list[RecruiterSearchHit] = []
        remaining_skip = offset
        remaining_take = limit
        for entity_type, count in segments:
            if remaining_take <= 0:
                break
            if remaining_skip >= count:
                remaining_skip -= count
                continue
            type_offset = remaining_skip
            type_limit = min(remaining_take, count - type_offset)
            remaining_skip = 0
            remaining_take -= type_limit
            if entity_type is RecruiterSearchEntityType.CANDIDATE:
                rows = self.search_repository.search_candidates(
                    company_id,
                    normalized,
                    branch_id=resolved_branch,
                    offset=type_offset,
                    limit=type_limit,
                )
                items.extend(self._candidate_hit(row) for row in rows)
            elif entity_type is RecruiterSearchEntityType.JOB:
                rows = self.search_repository.search_jobs(
                    company_id,
                    normalized,
                    branch_id=resolved_branch,
                    offset=type_offset,
                    limit=type_limit,
                )
                items.extend(self._job_hit(row) for row in rows)
            else:
                rows = self.search_repository.search_applications(
                    company_id,
                    normalized,
                    branch_id=resolved_branch,
                    offset=type_offset,
                    limit=type_limit,
                )
                items.extend(self._application_hit(row) for row in rows)

        return RecruiterSearchResponse(
            query=normalized,
            items=items,
            total=candidate_total + job_total + application_total,
            offset=offset,
            limit=limit,
            candidate_total=candidate_total,
            job_total=job_total,
            application_total=application_total,
        )
