from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.note import Note
from app.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    """Repository for recruiter/candidate notes."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Note)

    def list_by_candidate(self, candidate_id: str) -> list[Note]:
        statement = select(Note).where(Note.candidate_id == candidate_id).order_by(Note.created_at.desc())
        return list(self.db.scalars(statement).all())

    def list_pinned_by_candidate(self, candidate_id: str) -> list[Note]:
        statement = select(Note).where(Note.candidate_id == candidate_id, Note.pinned.is_(True)).order_by(Note.created_at.desc())
        return list(self.db.scalars(statement).all())

    def list_by_author(self, author_id: str) -> list[Note]:
        statement = select(Note).where(Note.author_id == author_id).order_by(Note.created_at.desc())
        return list(self.db.scalars(statement).all())
