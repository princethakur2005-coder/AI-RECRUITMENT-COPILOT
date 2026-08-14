"""Interview calendar sync persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.interview_calendar_sync import InterviewCalendarSync
from app.repositories.base import BaseRepository


class InterviewCalendarSyncRepository(BaseRepository[InterviewCalendarSync]):
    def __init__(self, db) -> None:  # noqa: ANN001
        super().__init__(db, InterviewCalendarSync)

    def get_by_interview_id(self, interview_id: UUID) -> InterviewCalendarSync | None:
        statement = select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_id == interview_id
        )
        return self.db.scalar(statement)

    def get_for_company(self, sync_id: UUID, company_id: UUID) -> InterviewCalendarSync | None:
        statement = select(InterviewCalendarSync).where(
            InterviewCalendarSync.id == sync_id,
            InterviewCalendarSync.company_id == company_id,
        )
        return self.db.scalar(statement)

    def get_or_create_for_interview(
        self,
        *,
        interview_id: UUID,
        company_id: UUID,
        calendar_integration_id: UUID | None,
        sync_status: str,
        commit: bool = False,
    ) -> InterviewCalendarSync:
        existing = self.get_by_interview_id(interview_id)
        if existing is not None:
            return existing
        row = InterviewCalendarSync(
            interview_id=interview_id,
            company_id=company_id,
            calendar_integration_id=calendar_integration_id,
            sync_status=sync_status,
        )
        return self.create(row, commit=commit)
