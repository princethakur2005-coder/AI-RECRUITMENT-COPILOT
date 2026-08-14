from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.core.notification import NotificationRecipientType, NotificationStatus
from app.models.notification import Notification
from app.repositories.base import BaseRepository
from app.schemas.notification import NotificationFilter


class NotificationRepository(BaseRepository[Notification]):
    """Persistence access for in-app notifications."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Notification)

    def _base_query(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None,
        filters: NotificationFilter | None,
    ) -> Select[tuple[Notification]]:
        query = filters or NotificationFilter()
        statement = select(Notification).where(
            Notification.recipient_type == recipient_type.value,
            Notification.recipient_id == recipient_id,
        )
        if company_ids is not None:
            statement = statement.where(Notification.company_id.in_(company_ids))
        if query.category is not None:
            statement = statement.where(Notification.category == query.category.value)
        if query.priority is not None:
            statement = statement.where(Notification.priority == query.priority.value)
        if query.status is not None:
            statement = statement.where(Notification.status == query.status.value)
        if query.created_after is not None:
            statement = statement.where(Notification.created_at >= query.created_after)
        if query.created_before is not None:
            statement = statement.where(Notification.created_at <= query.created_before)
        return statement

    def list_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None = None,
        filters: NotificationFilter | None = None,
    ) -> list[Notification]:
        query = filters or NotificationFilter()
        statement = (
            self._base_query(
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                company_ids=company_ids,
                filters=query,
            )
            .order_by(Notification.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )
        return list(self.db.scalars(statement).all())

    def count_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None = None,
        filters: NotificationFilter | None = None,
        status: NotificationStatus | None = None,
    ) -> int:
        query = filters or NotificationFilter()
        statement = self._base_query(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_ids=company_ids,
            filters=query,
        )
        if status is not None:
            statement = statement.where(Notification.status == status.value)
        count_statement = select(func.count()).select_from(statement.subquery())
        return int(self.db.scalar(count_statement) or 0)

    def get_owned(
        self,
        *,
        notification_id: UUID,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None = None,
    ) -> Notification | None:
        statement = select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_type == recipient_type.value,
            Notification.recipient_id == recipient_id,
        )
        if company_ids is not None:
            statement = statement.where(Notification.company_id.in_(company_ids))
        return self.db.scalar(statement)

    def mark_all_read_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None = None,
    ) -> int:
        """Bulk-update unread rows for one authenticated recipient scope."""
        now = datetime.now(timezone.utc)
        statement = (
            update(Notification)
            .where(
                Notification.recipient_type == recipient_type.value,
                Notification.recipient_id == recipient_id,
                Notification.status == NotificationStatus.UNREAD.value,
            )
            .values(
                status=NotificationStatus.READ.value,
                read_at=now,
                updated_at=now,
            )
        )
        if company_ids is not None:
            statement = statement.where(Notification.company_id.in_(company_ids))
        result = self.db.execute(statement)
        self.db.commit()
        return int(result.rowcount or 0)
