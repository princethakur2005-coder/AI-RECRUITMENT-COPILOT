from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[Candidate]):
    """Repository for candidate-specific persistence and lookup operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Candidate)

    def get_by_email(self, email: str) -> Candidate | None:
        normalized = email.strip().lower()
        statement = select(Candidate).where(func.lower(Candidate.email) == normalized)
        return self.db.scalar(statement)

    def set_password(self, candidate: Candidate, hashed_password: str) -> Candidate:
        return self.update(candidate, {"hashed_password": hashed_password})

    def search_by_skill(self, skill: str) -> list[Candidate]:
        statement = select(Candidate).where(Candidate.skills.ilike(f"%{skill}%"))
        return list(self.db.scalars(statement).all())

    def search_by_status(self, status: str) -> list[Candidate]:
        statement = select(Candidate).where(Candidate.status == status)
        return list(self.db.scalars(statement).all())
