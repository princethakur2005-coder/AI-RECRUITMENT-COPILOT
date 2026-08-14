from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job import Job


def _like_pattern(query: str) -> str:
    escaped = (
        query.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


class SearchRepository:
    """Company-scoped keyword search over recruiter ATS entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _job_scope(self, company_id: UUID, branch_id: UUID | None) -> list:
        filters = [Job.company_id == company_id]
        if branch_id is not None:
            filters.append(Job.branch_id == branch_id)
        return filters

    def _candidate_base(
        self,
        company_id: UUID,
        pattern: str,
        *,
        branch_id: UUID | None = None,
    ) -> Select:
        statement = (
            select(Candidate)
            .join(Application, Application.candidate_id == Candidate.id)
            .where(
                Application.company_id == company_id,
                or_(
                    Candidate.full_name.ilike(pattern, escape="\\"),
                    Candidate.email.ilike(pattern, escape="\\"),
                ),
            )
        )
        if branch_id is not None:
            statement = statement.join(Job, Job.id == Application.job_id).where(Job.branch_id == branch_id)
        return statement.distinct()

    def search_candidates(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Candidate]:
        pattern = _like_pattern(query)
        statement = (
            self._candidate_base(company_id, pattern, branch_id=branch_id)
            .order_by(Candidate.full_name.asc(), Candidate.id.asc())
            .offset(max(0, offset))
            .limit(max(0, limit))
        )
        return list(self.db.scalars(statement).unique().all())

    def count_candidates(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
    ) -> int:
        pattern = _like_pattern(query)
        subquery = (
            self._candidate_base(company_id, pattern, branch_id=branch_id)
            .with_only_columns(Candidate.id, maintain_column_froms=True)
            .distinct()
            .subquery()
        )
        total = self.db.scalar(select(func.count()).select_from(subquery))
        return int(total or 0)

    def search_jobs(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Job]:
        pattern = _like_pattern(query)
        statement = (
            select(Job)
            .where(
                *self._job_scope(company_id, branch_id),
                or_(
                    Job.title.ilike(pattern, escape="\\"),
                    Job.department.ilike(pattern, escape="\\"),
                    Job.location.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Job.title.asc(), Job.id.asc())
            .offset(max(0, offset))
            .limit(max(0, limit))
        )
        return list(self.db.scalars(statement).all())

    def count_jobs(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
    ) -> int:
        pattern = _like_pattern(query)
        total = self.db.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                *self._job_scope(company_id, branch_id),
                or_(
                    Job.title.ilike(pattern, escape="\\"),
                    Job.department.ilike(pattern, escape="\\"),
                    Job.location.ilike(pattern, escape="\\"),
                ),
            )
        )
        return int(total or 0)

    def _application_match_filters(self, company_id: UUID, pattern: str, branch_id: UUID | None):
        filters = [
            Application.company_id == company_id,
            or_(
                Application.status.ilike(pattern, escape="\\"),
                Candidate.full_name.ilike(pattern, escape="\\"),
                Candidate.email.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
            ),
        ]
        if branch_id is not None:
            filters.append(Job.branch_id == branch_id)
        return filters

    def _application_base(
        self,
        company_id: UUID,
        pattern: str,
        *,
        branch_id: UUID | None = None,
        load_relationships: bool = False,
    ) -> Select:
        statement = (
            select(Application)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(*self._application_match_filters(company_id, pattern, branch_id))
        )
        if load_relationships:
            statement = statement.options(
                joinedload(Application.candidate),
                joinedload(Application.job),
            )
        return statement

    def search_applications(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Application]:
        pattern = _like_pattern(query)
        statement = (
            self._application_base(
                company_id, pattern, branch_id=branch_id, load_relationships=True
            )
            .order_by(Candidate.full_name.asc(), Application.id.asc())
            .offset(max(0, offset))
            .limit(max(0, limit))
        )
        return list(self.db.scalars(statement).unique().all())

    def count_applications(
        self,
        company_id: UUID,
        query: str,
        *,
        branch_id: UUID | None = None,
    ) -> int:
        pattern = _like_pattern(query)
        subquery = (
            select(Application.id)
            .join(Candidate, Candidate.id == Application.candidate_id)
            .join(Job, Job.id == Application.job_id)
            .where(*self._application_match_filters(company_id, pattern, branch_id))
            .distinct()
            .subquery()
        )
        total = self.db.scalar(select(func.count()).select_from(subquery))
        return int(total or 0)
