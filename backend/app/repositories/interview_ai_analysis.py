from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.interview import Interview
from app.models.interview_ai_analysis import InterviewAIAnalysis
from app.repositories.base import BaseRepository


class InterviewAIAnalysisRepository(BaseRepository[InterviewAIAnalysis]):
    """Repository for interview AI analysis persistence."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, InterviewAIAnalysis)

    def get_by_interview_id(self, interview_id: UUID) -> InterviewAIAnalysis | None:
        statement = select(InterviewAIAnalysis).where(
            InterviewAIAnalysis.interview_id == interview_id,
        )
        return self.db.scalar(statement)

    def get_by_interview_id_for_company(
        self,
        interview_id: UUID,
        company_id: UUID,
    ) -> InterviewAIAnalysis | None:
        statement = (
            select(InterviewAIAnalysis)
            .join(Interview, InterviewAIAnalysis.interview_id == Interview.id)
            .where(
                InterviewAIAnalysis.interview_id == interview_id,
                Interview.company_id == company_id,
            )
        )
        return self.db.scalar(statement)

    def get_by_id_for_company(self, analysis_id: UUID, company_id: UUID) -> InterviewAIAnalysis | None:
        statement = (
            select(InterviewAIAnalysis)
            .join(Interview, InterviewAIAnalysis.interview_id == Interview.id)
            .where(
                InterviewAIAnalysis.id == analysis_id,
                Interview.company_id == company_id,
            )
        )
        return self.db.scalar(statement)

    def delete_by_interview_id(self, interview_id: UUID) -> None:
        existing = self.get_by_interview_id(interview_id)
        if existing is not None:
            self.delete(existing)

    def list_by_application_id_for_company(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> list[InterviewAIAnalysis]:
        statement = (
            select(InterviewAIAnalysis)
            .join(Interview, InterviewAIAnalysis.interview_id == Interview.id)
            .options(joinedload(InterviewAIAnalysis.interview))
            .where(
                Interview.company_id == company_id,
                Interview.application_id == application_id,
            )
            .order_by(InterviewAIAnalysis.updated_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def list_by_prompt_version_for_company(
        self,
        company_id: UUID,
        prompt_version: str,
    ) -> list[InterviewAIAnalysis]:
        statement = (
            select(InterviewAIAnalysis)
            .join(Interview, InterviewAIAnalysis.interview_id == Interview.id)
            .where(
                Interview.company_id == company_id,
                InterviewAIAnalysis.prompt_version == prompt_version,
            )
            .order_by(InterviewAIAnalysis.updated_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def exists_for_interview(self, interview_id: UUID) -> bool:
        return self.get_by_interview_id(interview_id) is not None

    def get_prompt_version_for_interview(self, interview_id: UUID) -> str | None:
        existing = self.get_by_interview_id(interview_id)
        if existing is None:
            return None
        return existing.prompt_version
