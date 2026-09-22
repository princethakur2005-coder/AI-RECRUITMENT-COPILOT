from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.application import Application
from app.models.candidate import Candidate
from app.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[Candidate]):
    """Repository for candidate-specific persistence and lookup operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Candidate)

    def get_by_id(self, obj_id: Any) -> Candidate | None:
        try:
            cid = UUID(str(obj_id)) if not isinstance(obj_id, UUID) else obj_id
        except (ValueError, TypeError):
            return None
        statement = (
            select(Candidate)
            .options(
                selectinload(Candidate.applications).selectinload(Application.ai_analysis),
                selectinload(Candidate.applications).selectinload(Application.assessment_sessions),
                selectinload(Candidate.applications).selectinload(Application.interview_sessions),
                selectinload(Candidate.applications).selectinload(Application.interviews),
                selectinload(Candidate.notes),
            )
            .where(Candidate.id == cid)
        )
        return self.db.scalar(statement)

    def get_all(self) -> list[Candidate]:
        statement = (
            select(Candidate)
            .options(
                selectinload(Candidate.applications).selectinload(Application.ai_analysis),
                selectinload(Candidate.applications).selectinload(Application.assessment_sessions),
                selectinload(Candidate.applications).selectinload(Application.interview_sessions),
                selectinload(Candidate.applications).selectinload(Application.interviews),
                selectinload(Candidate.notes),
            )
        )
        return list(self.db.scalars(statement).unique().all())

    def get_by_email(self, email: str) -> Candidate | None:
        normalized = email.strip().lower()
        statement = (
            select(Candidate)
            .options(
                selectinload(Candidate.applications).selectinload(Application.ai_analysis),
                selectinload(Candidate.applications).selectinload(Application.assessment_sessions),
                selectinload(Candidate.applications).selectinload(Application.interview_sessions),
                selectinload(Candidate.applications).selectinload(Application.interviews),
                selectinload(Candidate.notes),
            )
            .where(func.lower(Candidate.email) == normalized)
        )
        return self.db.scalar(statement)

    def set_password(self, candidate: Candidate, hashed_password: str) -> Candidate:
        return self.update(candidate, {"hashed_password": hashed_password})

    def search_by_skill(self, skill: str) -> list[Candidate]:
        statement = select(Candidate).where(Candidate.skills.ilike(f"%{skill}%"))
        return list(self.db.scalars(statement).all())

    def search_by_status(self, status: str) -> list[Candidate]:
        statement = select(Candidate).where(Candidate.status == status)
        return list(self.db.scalars(statement).all())
