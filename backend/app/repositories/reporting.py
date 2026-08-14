from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.application_status import ApplicationStatus, PIPELINE_STATUSES
from app.core.interview_status import InterviewStatus
from app.core.offer_status import OfferStatus
from app.models.application import Application
from app.models.interview import Interview
from app.models.job import Job
from app.models.offer import Offer


@dataclass(frozen=True, slots=True)
class ReportingQueryScope:
    company_id: UUID
    branch_id: UUID | None = None
    job_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def _complete_status_counts(raw: dict[str, int], statuses: tuple[str, ...]) -> dict[str, int]:
    return {status: int(raw.get(status, 0)) for status in statuses}


class ReportingRepository:
    """Read-only SQL aggregations for tenant-scoped reporting."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _date_filters(self, column: ColumnElement, scope: ReportingQueryScope) -> list[ColumnElement]:
        filters: list[ColumnElement] = []
        if scope.date_from is not None:
            filters.append(column >= scope.date_from)
        if scope.date_to is not None:
            filters.append(column <= scope.date_to)
        return filters

    def _application_filters(self, scope: ReportingQueryScope) -> list[ColumnElement]:
        filters: list[ColumnElement] = [Application.company_id == scope.company_id]
        if scope.job_id is not None:
            filters.append(Application.job_id == scope.job_id)
        if scope.branch_id is not None:
            filters.append(Job.branch_id == scope.branch_id)
        return filters

    def _join_jobs_for_branch(self, statement: Select, scope: ReportingQueryScope, job_id_column: ColumnElement) -> Select:
        if scope.branch_id is None:
            return statement
        return statement.join(Job, Job.id == job_id_column)

    def _scope_interviews(self, statement: Select, scope: ReportingQueryScope) -> Select:
        statement = statement.where(Interview.company_id == scope.company_id)
        if scope.job_id is None and scope.branch_id is None:
            return statement
        statement = statement.join(Application, Application.id == Interview.application_id)
        if scope.job_id is not None:
            statement = statement.where(Application.job_id == scope.job_id)
        if scope.branch_id is not None:
            statement = statement.join(Job, Job.id == Application.job_id).where(Job.branch_id == scope.branch_id)
        return statement

    def _scope_offers(self, statement: Select, scope: ReportingQueryScope) -> Select:
        statement = statement.join(Application, Offer.application_id == Application.id).where(
            Application.company_id == scope.company_id,
            Offer.application_id.is_not(None),
        )
        if scope.job_id is not None:
            statement = statement.where(Application.job_id == scope.job_id)
        if scope.branch_id is not None:
            statement = statement.join(Job, Job.id == Application.job_id).where(Job.branch_id == scope.branch_id)
        return statement

    def count_applications(self, scope: ReportingQueryScope) -> int:
        statement = select(func.count(Application.id)).where(*self._application_filters(scope))
        statement = self._join_jobs_for_branch(statement, scope, Application.job_id)
        statement = statement.where(*self._date_filters(Application.applied_at, scope))
        return int(self.db.scalar(statement) or 0)

    def count_applications_by_status(self, scope: ReportingQueryScope) -> dict[str, int]:
        statement = (
            select(Application.status, func.count(Application.id))
            .where(*self._application_filters(scope))
            .where(*self._date_filters(Application.applied_at, scope))
            .group_by(Application.status)
        )
        statement = self._join_jobs_for_branch(statement, scope, Application.job_id)
        rows = self.db.execute(statement).all()
        raw = {str(status): int(count) for status, count in rows}
        return _complete_status_counts(raw, tuple(status.value for status in PIPELINE_STATUSES))

    def count_hires(self, scope: ReportingQueryScope) -> int:
        statement = (
            select(func.count(Application.id))
            .where(*self._application_filters(scope))
            .where(Application.status == ApplicationStatus.HIRED.value)
            .where(*self._date_filters(Application.updated_at, scope))
        )
        statement = self._join_jobs_for_branch(statement, scope, Application.job_id)
        return int(self.db.scalar(statement) or 0)

    def count_interviews_by_status(self, scope: ReportingQueryScope) -> dict[str, int]:
        statement = self._scope_interviews(
            select(Interview.status, func.count(Interview.id)),
            scope,
        )
        statement = statement.where(*self._date_filters(Interview.scheduled_start, scope)).group_by(Interview.status)
        rows = self.db.execute(statement).all()
        raw = {str(status): int(count) for status, count in rows}
        return _complete_status_counts(raw, tuple(status.value for status in InterviewStatus))

    def count_interviews(self, scope: ReportingQueryScope) -> int:
        statement = self._scope_interviews(select(func.count(Interview.id)), scope)
        statement = statement.where(*self._date_filters(Interview.scheduled_start, scope))
        return int(self.db.scalar(statement) or 0)

    def count_offers_by_status(self, scope: ReportingQueryScope) -> dict[str, int]:
        statement = self._scope_offers(select(Offer.status, func.count(Offer.id)), scope)
        statement = statement.where(*self._date_filters(Offer.created_at, scope)).group_by(Offer.status)
        rows = self.db.execute(statement).all()
        raw = {str(status): int(count) for status, count in rows}
        return _complete_status_counts(raw, tuple(status.value for status in OfferStatus))

    def count_offers(self, scope: ReportingQueryScope) -> int:
        statement = self._scope_offers(select(func.count(Offer.id)), scope)
        statement = statement.where(*self._date_filters(Offer.created_at, scope))
        return int(self.db.scalar(statement) or 0)

    def _series(self, statement: Select) -> list[tuple[str, int]]:
        rows = self.db.execute(statement).all()
        return [(str(period), int(count)) for period, count in rows]

    def applications_over_time(self, scope: ReportingQueryScope) -> list[tuple[str, int]]:
        period = func.date(Application.applied_at)
        statement = (
            select(period.label("period"), func.count(Application.id))
            .where(*self._application_filters(scope))
            .where(*self._date_filters(Application.applied_at, scope))
            .group_by(period)
            .order_by(period.asc())
        )
        statement = self._join_jobs_for_branch(statement, scope, Application.job_id)
        return self._series(statement)

    def interviews_over_time(self, scope: ReportingQueryScope) -> list[tuple[str, int]]:
        period = func.date(Interview.scheduled_start)
        statement = self._scope_interviews(
            select(period.label("period"), func.count(Interview.id)),
            scope,
        )
        statement = (
            statement.where(*self._date_filters(Interview.scheduled_start, scope))
            .group_by(period)
            .order_by(period.asc())
        )
        return self._series(statement)

    def hires_over_time(self, scope: ReportingQueryScope) -> list[tuple[str, int]]:
        period = func.date(Application.updated_at)
        statement = (
            select(period.label("period"), func.count(Application.id))
            .where(*self._application_filters(scope))
            .where(Application.status == ApplicationStatus.HIRED.value)
            .where(*self._date_filters(Application.updated_at, scope))
            .group_by(period)
            .order_by(period.asc())
        )
        statement = self._join_jobs_for_branch(statement, scope, Application.job_id)
        return self._series(statement)
