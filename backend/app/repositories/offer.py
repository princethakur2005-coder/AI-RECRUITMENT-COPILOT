from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.offer import Offer
from app.repositories.base import BaseRepository


class OfferRepository(BaseRepository[Offer]):
    """Repository for application-owned offer persistence with tenant-safe access."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Offer)

    def get_by_id_for_company(self, offer_id: UUID, company_id: UUID) -> Offer | None:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .options(
                joinedload(Offer.application).joinedload(Application.candidate),
                joinedload(Offer.application).joinedload(Application.job),
            )
            .where(
                Offer.id == offer_id,
                Application.company_id == company_id,
            )
        )
        return self.db.scalars(statement).unique().first()

    def list_by_application_id_for_company(
        self,
        company_id: UUID,
        application_id: UUID,
        *,
        active_only: bool = False,
    ) -> list[Offer]:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Offer.application_id == application_id,
            )
            .order_by(Offer.revision.desc(), Offer.created_at.desc())
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return list(self.db.scalars(statement).all())

    def get_active_by_application_id_for_company(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> Offer | None:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Offer.application_id == application_id,
                Offer.is_active.is_(True),
            )
            .order_by(Offer.revision.desc(), Offer.created_at.desc())
        )
        return self.db.scalars(statement).first()

    def list_by_job_id_for_company(
        self,
        company_id: UUID,
        job_id: UUID,
        *,
        active_only: bool = True,
    ) -> list[Offer]:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .options(joinedload(Offer.application).joinedload(Application.candidate))
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.created_at.desc())
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return list(self.db.scalars(statement).unique().all())

    def count_by_job_id_for_company(
        self,
        company_id: UUID,
        job_id: UUID,
        *,
        active_only: bool = True,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
                Offer.application_id.is_not(None),
            )
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return int(self.db.scalar(statement) or 0)

    def list_by_job_id_for_company_paginated(
        self,
        company_id: UUID,
        job_id: UUID,
        *,
        offset: int,
        limit: int,
        active_only: bool = True,
    ) -> list[Offer]:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .options(joinedload(Offer.application).joinedload(Application.candidate))
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.updated_at.desc(), Offer.revision.desc())
            .offset(max(0, offset))
            .limit(max(1, limit))
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return list(self.db.scalars(statement).unique().all())

    def list_active_lifecycle_offers_for_company(
        self,
        company_id: UUID,
        *,
        statuses: list[str] | None = None,
    ) -> list[Offer]:
        """Efficient company-scoped pending/in-flight offers for recruiter workspace."""
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .options(
                joinedload(Offer.application).joinedload(Application.candidate),
                joinedload(Offer.application).joinedload(Application.job),
            )
            .where(
                Application.company_id == company_id,
                Offer.is_active.is_(True),
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.updated_at.desc(), Offer.revision.desc())
        )
        if statuses:
            statement = statement.where(Offer.status.in_(statuses))
        return list(self.db.scalars(statement).unique().all())

    def list_by_candidate_id_for_company(
        self,
        company_id: UUID,
        candidate_id: UUID,
        *,
        active_only: bool = False,
    ) -> list[Offer]:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Application.candidate_id == candidate_id,
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.created_at.desc(), Offer.revision.desc())
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return list(self.db.scalars(statement).all())

    def list_owned_by_candidate(self, candidate_id: UUID, *, active_only: bool = False) -> list[Offer]:
        """Candidate-portal: application-owned offers for the authenticated candidate."""
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.candidate_id == candidate_id,
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.created_at.desc(), Offer.revision.desc())
        )
        if active_only:
            statement = statement.where(Offer.is_active.is_(True))
        return list(self.db.scalars(statement).all())

    def get_owned_by_candidate(self, offer_id: UUID, candidate_id: UUID) -> Offer | None:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Offer.id == offer_id,
                Application.candidate_id == candidate_id,
                Offer.application_id.is_not(None),
            )
        )
        return self.db.scalars(statement).first()

    def list_by_status_for_company(self, company_id: UUID, status: str) -> list[Offer]:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Offer.status == status,
                Offer.application_id.is_not(None),
            )
            .order_by(Offer.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def next_revision_for_application(self, application_id: UUID) -> int:
        statement = (
            select(Offer.revision)
            .where(Offer.application_id == application_id)
            .order_by(Offer.revision.desc())
            .limit(1)
        )
        current = self.db.scalar(statement)
        return int(current or 0) + 1

    def get_latest_by_application_id_for_company(
        self,
        company_id: UUID,
        application_id: UUID,
    ) -> Offer | None:
        statement = (
            select(Offer)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Offer.application_id == application_id,
            )
            .order_by(Offer.revision.desc(), Offer.created_at.desc())
            .limit(1)
        )
        return self.db.scalars(statement).first()
