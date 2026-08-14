from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.application_hiring_decision import ApplicationHiringDecision
from app.repositories.base import BaseRepository


class ApplicationHiringDecisionRepository(BaseRepository[ApplicationHiringDecision]):
    """Repository for application hiring decision persistence."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, ApplicationHiringDecision)

    def get_by_application_id(self, application_id: UUID) -> ApplicationHiringDecision | None:
        statement = select(ApplicationHiringDecision).where(
            ApplicationHiringDecision.application_id == application_id,
        )
        return self.db.scalar(statement)

    def get_by_application_id_for_company(
        self,
        application_id: UUID,
        company_id: UUID,
    ) -> ApplicationHiringDecision | None:
        statement = (
            select(ApplicationHiringDecision)
            .join(Application, ApplicationHiringDecision.application_id == Application.id)
            .where(
                ApplicationHiringDecision.application_id == application_id,
                Application.company_id == company_id,
            )
        )
        return self.db.scalar(statement)

    def get_by_id_for_company(
        self,
        decision_id: UUID,
        company_id: UUID,
    ) -> ApplicationHiringDecision | None:
        statement = (
            select(ApplicationHiringDecision)
            .join(Application, ApplicationHiringDecision.application_id == Application.id)
            .where(
                ApplicationHiringDecision.id == decision_id,
                Application.company_id == company_id,
            )
        )
        return self.db.scalar(statement)

    def list_by_job_id_for_company(
        self,
        company_id: UUID,
        job_id: UUID,
    ) -> list[ApplicationHiringDecision]:
        statement = (
            select(ApplicationHiringDecision)
            .join(Application, ApplicationHiringDecision.application_id == Application.id)
            .options(
                joinedload(ApplicationHiringDecision.application).joinedload(Application.candidate),
            )
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
            )
            .order_by(ApplicationHiringDecision.overall_score.desc(), ApplicationHiringDecision.updated_at.desc())
        )
        return list(self.db.scalars(statement).unique().all())

    def count_by_job_id_for_company(self, company_id: UUID, job_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ApplicationHiringDecision)
            .join(Application, ApplicationHiringDecision.application_id == Application.id)
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
            )
        )
        return int(self.db.scalar(statement) or 0)

    def list_by_job_id_for_company_paginated(
        self,
        company_id: UUID,
        job_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> list[ApplicationHiringDecision]:
        statement = (
            select(ApplicationHiringDecision)
            .join(Application, ApplicationHiringDecision.application_id == Application.id)
            .options(
                joinedload(ApplicationHiringDecision.application).joinedload(Application.candidate),
            )
            .where(
                Application.company_id == company_id,
                Application.job_id == job_id,
            )
            .order_by(ApplicationHiringDecision.overall_score.desc(), ApplicationHiringDecision.updated_at.desc())
            .offset(max(0, offset))
            .limit(max(1, limit))
        )
        return list(self.db.scalars(statement).unique().all())

    def delete_by_application_id(self, application_id: UUID) -> None:
        existing = self.get_by_application_id(application_id)
        if existing is not None:
            self.delete(existing)

    def exists_for_application(self, application_id: UUID) -> bool:
        return self.get_by_application_id(application_id) is not None

    def get_policy_version_for_application(self, application_id: UUID) -> str | None:
        existing = self.get_by_application_id(application_id)
        if existing is None:
            return None
        return existing.policy_version
