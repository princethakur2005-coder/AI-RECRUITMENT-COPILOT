"""Webhook configuration persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.webhook import Webhook
from app.repositories.base import BaseRepository


class WebhookRepository(BaseRepository[Webhook]):
    def __init__(self, db) -> None:  # noqa: ANN001
        super().__init__(db, Webhook)

    def list_by_company(self, company_id: UUID) -> list[Webhook]:
        statement = (
            select(Webhook)
            .where(Webhook.company_id == company_id)
            .order_by(Webhook.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_for_company(self, webhook_id: UUID, company_id: UUID) -> Webhook | None:
        statement = select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.company_id == company_id,
        )
        return self.db.scalar(statement)

    def list_active_for_event(self, company_id: UUID, event_type: str) -> list[Webhook]:
        """Return active webhooks for a company that subscribe to ``event_type``.

        Event matching is performed in Python so SQLite/Postgres JSON shapes stay simple.
        """
        statement = select(Webhook).where(
            Webhook.company_id == company_id,
            Webhook.is_active.is_(True),
        )
        rows = list(self.db.scalars(statement).all())
        return [row for row in rows if event_type in set(row.event_types)]
