from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.schemas.activity_timeline import (
    ActivityTimelineCreate,
    ActivityTimelineFilter,
    ActivityTimelineItem,
    ActivityTimelineListResponse,
)
from app.services.audit_service import AuditService, audit_service
from app.services.notification import NotificationService


class ActivityTimelineService:
    """Unified activity feed built from audit, notifications, and manual events."""

    def __init__(
        self,
        audit_log_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.audit_log_service = audit_log_service or audit_service
        self.notification_service = notification_service
        self._manual_items: list[ActivityTimelineItem] = []
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def create_activity(self, payload: ActivityTimelineCreate) -> ActivityTimelineItem:
        item = ActivityTimelineItem(
            id=str(uuid4()),
            timestamp=payload.timestamp or self._now_provider(),
            source="activity_timeline",
            activity_type=payload.activity_type,
            actor_id=payload.actor_id,
            actor_type=payload.actor_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            previous_state=dict(payload.previous_state or {}),
            current_state=dict(payload.current_state or {}),
            metadata=dict(payload.metadata or {}),
        )
        self._manual_items.append(item)
        return item

    def list_activities(self, filters: ActivityTimelineFilter | None = None) -> ActivityTimelineListResponse:
        query = filters or ActivityTimelineFilter()

        records: list[ActivityTimelineItem] = []
        if query.include_audit:
            records.extend(self._collect_audit_items(query))
        if query.include_notifications:
            records.extend(self._collect_notification_items(query))
        if query.include_manual:
            records.extend(self._collect_manual_items(query))

        records.sort(key=lambda item: str(item.timestamp), reverse=True)
        total = len(records)
        paged = records[query.offset : query.offset + query.limit]
        return ActivityTimelineListResponse(items=paged, total=total)

    def get_timeline(self, filters: ActivityTimelineFilter | None = None) -> ActivityTimelineListResponse:
        return self.list_activities(filters=filters)

    def get_entity_timeline(
        self,
        entity_type: str,
        entity_id: str,
        activity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ActivityTimelineListResponse:
        return self.list_activities(
            ActivityTimelineFilter(
                entity_type=entity_type,
                entity_id=entity_id,
                activity_type=activity_type,
                limit=limit,
                offset=offset,
            )
        )

    def _collect_audit_items(self, filters: ActivityTimelineFilter) -> list[ActivityTimelineItem]:
        audit_events = self.audit_log_service.filter_events(
            actor_id=filters.actor_id,
            actor_type=filters.actor_type,
            resource_type=filters.entity_type,
            resource_id=filters.entity_id,
            entity_type=filters.entity_type,
            entity_id=filters.entity_id,
            action=filters.activity_type,
            since=filters.since,
            until=filters.until,
        )

        items: list[ActivityTimelineItem] = []
        for event in audit_events:
            items.append(
                ActivityTimelineItem(
                    id=str(event.get("id") or uuid4()),
                    timestamp=event.get("timestamp") or self._now_provider(),
                    source="audit",
                    activity_type=str(event.get("action") or "unknown"),
                    actor_id=event.get("actor_id"),
                    actor_type=event.get("actor_type"),
                    entity_type=str(
                        event.get("entity_type")
                        or event.get("resource_type")
                        or "unknown"
                    ),
                    entity_id=event.get("entity_id") or event.get("resource_id"),
                    previous_state=dict(event.get("previous_state") or {}),
                    current_state=dict(event.get("current_state") or {}),
                    metadata=dict(event.get("metadata") or {}),
                )
            )
        return items

    def _collect_notification_items(self, filters: ActivityTimelineFilter) -> list[ActivityTimelineItem]:
        if self.notification_service is None:
            return []

        notification_list = self.notification_service.list_notifications()
        items: list[ActivityTimelineItem] = []

        for notification in notification_list.items:
            entity_type = "notification"
            entity_id = str(notification.id)
            activity_type = "notification.created"
            actor_id = None
            actor_type = None
            metadata = dict(notification.metadata or {})
            metadata.update(
                {
                    "category": notification.category.value,
                    "priority": notification.priority.value,
                    "status": notification.status.value,
                    "title": notification.title,
                    "message": notification.message,
                    "recipient_id": str(notification.recipient_id),
                    "recipient_type": notification.recipient_type.value,
                }
            )

            if filters.user_id is not None and notification.recipient_id != filters.user_id:
                continue
            if filters.entity_type is not None and filters.entity_type != entity_type:
                continue
            if filters.entity_id is not None and filters.entity_id != entity_id:
                continue
            if filters.activity_type is not None and filters.activity_type != activity_type:
                continue
            if filters.source is not None and filters.source != "notification":
                continue

            item = ActivityTimelineItem(
                id=entity_id,
                timestamp=notification.created_at,
                source="notification",
                activity_type=activity_type,
                actor_id=actor_id,
                actor_type=actor_type,
                entity_type=entity_type,
                entity_id=entity_id,
                previous_state={},
                current_state={"status": notification.status.value},
                metadata=metadata,
            )

            timestamp = str(item.timestamp)
            if filters.since and timestamp < filters.since:
                continue
            if filters.until and timestamp > filters.until:
                continue

            items.append(item)

        return items

    def _collect_manual_items(self, filters: ActivityTimelineFilter) -> list[ActivityTimelineItem]:
        return [item for item in self._manual_items if self._matches(item, filters)]

    def _matches(self, item: ActivityTimelineItem, filters: ActivityTimelineFilter) -> bool:
        if filters.source is not None and item.source != filters.source:
            return False
        if filters.actor_id is not None and item.actor_id != filters.actor_id:
            return False
        if filters.actor_type is not None and item.actor_type != filters.actor_type:
            return False
        if filters.entity_type is not None and item.entity_type != filters.entity_type:
            return False
        if filters.entity_id is not None and item.entity_id != filters.entity_id:
            return False
        if filters.activity_type is not None and item.activity_type != filters.activity_type:
            return False

        timestamp = str(item.timestamp)
        if filters.since and timestamp < filters.since:
            return False
        if filters.until and timestamp > filters.until:
            return False
        return True


activity_timeline_service = ActivityTimelineService()
