"""Calendar integration persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.calendar import CalendarIntegrationStatus
from app.models.calendar_integration import CalendarIntegration
from app.repositories.base import BaseRepository


class CalendarIntegrationRepository(BaseRepository[CalendarIntegration]):
    def __init__(self, db) -> None:  # noqa: ANN001
        super().__init__(db, CalendarIntegration)

    def list_by_company(self, company_id: UUID) -> list[CalendarIntegration]:
        statement = (
            select(CalendarIntegration)
            .where(CalendarIntegration.company_id == company_id)
            .order_by(CalendarIntegration.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_for_company(self, integration_id: UUID, company_id: UUID) -> CalendarIntegration | None:
        statement = select(CalendarIntegration).where(
            CalendarIntegration.id == integration_id,
            CalendarIntegration.company_id == company_id,
        )
        return self.db.scalar(statement)

    def get_by_company_and_provider(
        self,
        company_id: UUID,
        provider_type: str,
    ) -> CalendarIntegration | None:
        statement = select(CalendarIntegration).where(
            CalendarIntegration.company_id == company_id,
            CalendarIntegration.provider_type == provider_type,
        )
        return self.db.scalar(statement)

    def get_active_for_company(self, company_id: UUID) -> CalendarIntegration | None:
        statement = (
            select(CalendarIntegration)
            .where(
                CalendarIntegration.company_id == company_id,
                CalendarIntegration.status == CalendarIntegrationStatus.ACTIVE.value,
            )
            .order_by(CalendarIntegration.updated_at.desc())
            .limit(1)
        )
        return self.db.scalar(statement)
