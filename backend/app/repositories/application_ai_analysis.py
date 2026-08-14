from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.repositories.base import BaseRepository


class ApplicationAIAnalysisRepository(BaseRepository[ApplicationAIAnalysis]):
    """Repository for application AI analysis persistence."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ApplicationAIAnalysis)

    def get_by_application_id(self, application_id: UUID) -> ApplicationAIAnalysis | None:
        statement = select(ApplicationAIAnalysis).where(
            ApplicationAIAnalysis.application_id == application_id,
        )
        return self.db.scalar(statement)

    def get_by_application_id_for_company(
        self,
        application_id: UUID,
        company_id: UUID,
    ) -> ApplicationAIAnalysis | None:
        statement = (
            select(ApplicationAIAnalysis)
            .join(Application, ApplicationAIAnalysis.application_id == Application.id)
            .where(
                ApplicationAIAnalysis.application_id == application_id,
                Application.company_id == company_id,
            )
        )
        return self.db.scalar(statement)

    def delete_by_application_id(self, application_id: UUID) -> None:
        existing = self.get_by_application_id(application_id)
        if existing is not None:
            self.delete(existing)
