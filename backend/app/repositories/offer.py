from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.offer import Offer
from app.repositories.base import BaseRepository


class OfferRepository(BaseRepository[Offer]):
    """Repository for offer lifecycle persistence."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Offer)

    def list_by_candidate(self, candidate_id: str) -> list[Offer]:
        statement = select(Offer).where(Offer.candidate_id == candidate_id).order_by(Offer.created_at.desc())
        return list(self.db.scalars(statement).all())

    def get_by_candidate_and_status(self, candidate_id: str, status: str) -> Offer | None:
        statement = select(Offer).where(Offer.candidate_id == candidate_id, Offer.status == status)
        return self.db.scalar(statement)

    def list_by_status(self, status: str) -> list[Offer]:
        statement = select(Offer).where(Offer.status == status).order_by(Offer.created_at.desc())
        return list(self.db.scalars(statement).all())
