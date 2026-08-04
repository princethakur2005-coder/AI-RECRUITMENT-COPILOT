from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Repository for company persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Company)

    def get_by_slug(self, slug: str) -> Company | None:
        statement = select(Company).where(Company.slug == slug)
        return self.db.scalar(statement)

    def slug_exists(self, slug: str) -> bool:
        return self.get_by_slug(slug) is not None

    def get_by_owner_id(self, owner_id: UUID) -> Company | None:
        statement = select(Company).where(Company.owner_id == owner_id)
        return self.db.scalar(statement)
