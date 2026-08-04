from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.interview_status import InterviewStatus
from app.models.application import Application
from app.models.company_member import CompanyMember
from app.models.interview import Interview
from app.repositories.base import BaseRepository


class InterviewRepository(BaseRepository[Interview]):
    """Repository for interview persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Interview)

    def _base_query_options(self):
        return (
            joinedload(Interview.interviewer_member).joinedload(CompanyMember.user),
            joinedload(Interview.application).joinedload(Application.candidate),
            joinedload(Interview.application).joinedload(Application.job),
        )

    def get_by_id_for_company(self, interview_id: UUID, company_id: UUID) -> Interview | None:
        statement = (
            select(Interview)
            .options(*self._base_query_options())
            .where(Interview.id == interview_id, Interview.company_id == company_id)
        )
        return self.db.scalars(statement).unique().first()

    def list_by_company_id(self, company_id: UUID) -> list[Interview]:
        statement = (
            select(Interview)
            .options(*self._base_query_options())
            .where(Interview.company_id == company_id)
            .order_by(Interview.scheduled_start.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def list_by_application_id(self, company_id: UUID, application_id: UUID) -> list[Interview]:
        statement = (
            select(Interview)
            .options(*self._base_query_options())
            .where(
                Interview.company_id == company_id,
                Interview.application_id == application_id,
            )
            .order_by(Interview.scheduled_start.asc())
        )
        return list(self.db.scalars(statement).unique().all())

    def count_by_application_id(self, application_id: UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Interview)
            .where(Interview.application_id == application_id),
        )
        return int(total or 0)

    def list_upcoming_for_company(self, company_id: UUID, limit: int = 10) -> list[Interview]:
        now = datetime.now(timezone.utc)
        statement = (
            select(Interview)
            .options(*self._base_query_options())
            .where(
                Interview.company_id == company_id,
                Interview.status == InterviewStatus.SCHEDULED,
                Interview.scheduled_start >= now,
            )
            .order_by(Interview.scheduled_start.asc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).unique().all())

    def count_scheduled_today_for_company(self, company_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day.replace(hour=23, minute=59, second=59, microsecond=999999)
        total = self.db.scalar(
            select(func.count())
            .select_from(Interview)
            .where(
                Interview.company_id == company_id,
                Interview.status == InterviewStatus.SCHEDULED,
                Interview.scheduled_start >= start_of_day,
                Interview.scheduled_start <= end_of_day,
            ),
        )
        return int(total or 0)
