from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.company_member import CompanyMember
from app.repositories.base import BaseRepository


class CompanyMemberRepository(BaseRepository[CompanyMember]):
    """Repository for company membership persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, CompanyMember)

    def get_by_company_and_user(self, company_id: UUID, user_id: UUID) -> CompanyMember | None:
        statement = (
            select(CompanyMember)
            .options(joinedload(CompanyMember.user))
            .where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user_id,
            )
        )
        return self.db.scalars(statement).unique().first()

    def get_by_user_id(self, user_id: UUID) -> CompanyMember | None:
        statement = select(CompanyMember).where(CompanyMember.user_id == user_id)
        return self.db.scalar(statement)

    def list_by_company_id(self, company_id: UUID) -> list[CompanyMember]:
        statement = (
            select(CompanyMember)
            .options(joinedload(CompanyMember.user))
            .where(CompanyMember.company_id == company_id)
            .order_by(CompanyMember.created_at.asc())
        )
        return list(self.db.scalars(statement).unique().all())

    def get_by_id_for_company(self, member_id: UUID, company_id: UUID) -> CompanyMember | None:
        statement = (
            select(CompanyMember)
            .options(joinedload(CompanyMember.user))
            .where(
                CompanyMember.id == member_id,
                CompanyMember.company_id == company_id,
            )
        )
        return self.db.scalars(statement).unique().first()
