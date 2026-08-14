from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.repositories.base import BaseRepository


class AuditEventRepository(BaseRepository[AuditEvent]):
    """Append-only persistence for tenant audit events."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, AuditEvent)

    def append(self, event: AuditEvent, *, commit: bool = True) -> AuditEvent:
        return self.create(event, commit=commit)

    def update(self, db_obj: AuditEvent, obj_in: dict, *, commit: bool = True) -> AuditEvent:
        raise PermissionError("Audit records are append-only")

    def delete(self, db_obj: AuditEvent, *, commit: bool = True) -> None:
        raise PermissionError("Audit records are append-only")

    def _scoped_query(
        self,
        company_id: UUID,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> Select[tuple[AuditEvent]]:
        statement = select(AuditEvent).where(AuditEvent.company_id == company_id)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        if resource_type is not None:
            statement = statement.where(AuditEvent.resource_type == resource_type)
        if resource_id is not None:
            statement = statement.where(AuditEvent.resource_id == resource_id)
        if actor_id is not None:
            statement = statement.where(AuditEvent.actor_id == actor_id)
        if actor_type is not None:
            statement = statement.where(AuditEvent.actor_type == actor_type)
        if created_after is not None:
            statement = statement.where(AuditEvent.created_at >= created_after)
        if created_before is not None:
            statement = statement.where(AuditEvent.created_at <= created_before)
        return statement

    def list_for_company(
        self,
        company_id: UUID,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditEvent]:
        statement = (
            self._scoped_query(
                company_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_id=actor_id,
                actor_type=actor_type,
                created_after=created_after,
                created_before=created_before,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def count_for_company(
        self,
        company_id: UUID,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(
            self._scoped_query(
                company_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_id=actor_id,
                actor_type=actor_type,
                created_after=created_after,
                created_before=created_before,
            ).subquery(),
        )
        return int(self.db.scalar(statement) or 0)
