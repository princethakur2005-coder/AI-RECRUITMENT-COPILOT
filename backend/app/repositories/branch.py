from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.repositories.base import BaseRepository


class BranchRepository(BaseRepository[Branch]):
    """Repository for branch persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Branch)

    def list_by_company_id(self, company_id: UUID) -> list[Branch]:
        statement = (
            select(Branch)
            .where(Branch.company_id == company_id)
            .order_by(Branch.name.asc())
        )
        return list(self.db.scalars(statement).all())

    def slug_exists_for_company(self, company_id: UUID, slug: str) -> bool:
        statement = select(Branch).where(
            Branch.company_id == company_id,
            Branch.slug == slug,
        )
        return self.db.scalar(statement) is not None
