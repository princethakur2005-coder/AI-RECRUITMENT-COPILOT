from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    """Repository for application persistence operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Application)

    def get_by_id_for_company(self, application_id: UUID, company_id: UUID) -> Application | None:
        statement = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(
                Application.id == application_id,
                Application.company_id == company_id,
            )
        )
        return self.db.scalars(statement).unique().first()

    def get_by_candidate_and_job(self, candidate_id: UUID, job_id: UUID) -> Application | None:
        statement = select(Application).where(
            Application.candidate_id == candidate_id,
            Application.job_id == job_id,
        )
        return self.db.scalar(statement)

    def list_by_company_id(self, company_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.company_id == company_id)
            .order_by(Application.applied_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def list_by_job_id(self, company_id: UUID, job_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
            )
            .order_by(Application.applied_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def list_by_candidate_id(self, company_id: UUID, candidate_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(
                Application.company_id == company_id,
                Application.candidate_id == candidate_id,
            )
            .order_by(Application.applied_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def count_by_status(self, company_id: UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.company_id == company_id)
            .group_by(Application.status),
        ).all()
        return {status: int(count) for status, count in rows}

    def count_total(self, company_id: UUID) -> int:
        total = self.db.scalar(
            select(func.count()).select_from(Application).where(Application.company_id == company_id),
        )
        return int(total or 0)

    def list_recent_for_company(self, company_id: UUID, limit: int = 20) -> list[Application]:
        statement = (
            select(Application)
            .options(
                joinedload(Application.candidate),
                joinedload(Application.job),
            )
            .where(Application.company_id == company_id)
            .order_by(Application.applied_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).unique().all())

    def list_for_dashboard(self, company_id: UUID) -> list[Application]:
        statement = (
            select(Application)
            .options(
                joinedload(Application.candidate),
                joinedload(Application.job),
            )
            .where(Application.company_id == company_id)
            .order_by(Application.applied_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())
