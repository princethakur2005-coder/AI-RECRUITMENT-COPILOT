from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

from app.schemas.notification import (
    NotificationCreate,
    NotificationFilter,
    NotificationHistoryEvent,
    NotificationListResponse,
    NotificationResponse,
    NotificationStatus,
)


class NotificationService:
    """Core in-process Notification Center service.

    This service is intentionally transport-agnostic so future delivery channels
    (email, background jobs, real-time gateways) can be integrated without
    changing the Notification Center contract.
    """

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._items: dict[UUID, NotificationResponse] = {}
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def create_notification(self, payload: NotificationCreate, actor_id: str | None = None) -> NotificationResponse:
        now = self._now_provider()
        notification = NotificationResponse(
            id=uuid4(),
            user_id=payload.user_id,
            title=payload.title,
            message=payload.message,
            category=payload.category,
            priority=payload.priority,
            status=NotificationStatus.UNREAD,
            metadata=dict(payload.metadata or {}),
            created_at=now,
            updated_at=now,
            history=[
                NotificationHistoryEvent(
                    event="created",
                    timestamp=now,
                    actor_id=actor_id,
                    details={"status": NotificationStatus.UNREAD.value},
                )
            ],
        )
        self._items[notification.id] = notification
        return notification

    def get_notification(self, notification_id: UUID, user_id: UUID | None = None) -> NotificationResponse | None:
        item = self._items.get(notification_id)
        if item is None:
            return None
        if user_id is not None and item.user_id != user_id:
            return None
        return item

    def mark_as_read(
        self,
        notification_id: UUID,
        user_id: UUID | None = None,
        actor_id: str | None = None,
    ) -> NotificationResponse | None:
        return self._update_status(
            notification_id=notification_id,
            next_status=NotificationStatus.READ,
            user_id=user_id,
            actor_id=actor_id,
        )

    def mark_as_unread(
        self,
        notification_id: UUID,
        user_id: UUID | None = None,
        actor_id: str | None = None,
    ) -> NotificationResponse | None:
        return self._update_status(
            notification_id=notification_id,
            next_status=NotificationStatus.UNREAD,
            user_id=user_id,
            actor_id=actor_id,
        )

    def list_notifications(self, filters: NotificationFilter | None = None) -> NotificationListResponse:
        query = filters or NotificationFilter()

        records = list(self._items.values())
        records = [item for item in records if self._matches(item, query)]
        records.sort(key=lambda item: item.created_at, reverse=True)

        total = len(records)
        paged = records[query.offset : query.offset + query.limit]
        unread_count = sum(1 for item in records if item.status == NotificationStatus.UNREAD)

        return NotificationListResponse(
            items=paged,
            total=total,
            unread_count=unread_count,
        )

    def get_notification_history(
        self,
        notification_id: UUID,
        user_id: UUID | None = None,
    ) -> list[NotificationHistoryEvent]:
        item = self.get_notification(notification_id=notification_id, user_id=user_id)
        if item is None:
            return []
        return list(item.history)

    def _update_status(
        self,
        notification_id: UUID,
        next_status: NotificationStatus,
        user_id: UUID | None,
        actor_id: str | None,
    ) -> NotificationResponse | None:
        item = self.get_notification(notification_id=notification_id, user_id=user_id)
        if item is None:
            return None

        if item.status == next_status:
            return item

        now = self._now_provider()
        previous_status = item.status
        item.status = next_status
        item.updated_at = now
        item.history.append(
            NotificationHistoryEvent(
                event="status_changed",
                timestamp=now,
                actor_id=actor_id,
                details={
                    "from": previous_status.value,
                    "to": next_status.value,
                },
            )
        )
        return item

    def _matches(self, item: NotificationResponse, filters: NotificationFilter) -> bool:
        if filters.user_id is not None and item.user_id != filters.user_id:
            return False
        if filters.category is not None and item.category != filters.category:
            return False
        if filters.priority is not None and item.priority != filters.priority:
            return False
        if filters.status is not None and item.status != filters.status:
            return False
        if filters.created_after is not None and item.created_at < filters.created_after:
            return False
        if filters.created_before is not None and item.created_at > filters.created_before:
            return False
        return True
