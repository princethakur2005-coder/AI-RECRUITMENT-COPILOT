from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.notification import (
    NotificationRecipientType,
    NotificationStatus,
)
from app.models.candidate import Candidate
from app.models.notification import Notification
from app.models.user import User
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.notification import NotificationRepository
from app.schemas.notification import (
    NotificationCreate,
    NotificationFilter,
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationResponse,
    NotificationSummaryResponse,
)


class NotificationService:
    """PostgreSQL-backed in-app Notification Center.

    Notifications are always persisted. Channel preferences gate email enqueue
    and in-app list/summary surfacing — never event creation itself.
    """

    def __init__(
        self,
        notification_repository: NotificationRepository,
        member_repository: CompanyMemberRepository,
        preference_service: Any | None = None,
    ) -> None:
        self.notification_repository = notification_repository
        self.member_repository = member_repository
        self.preference_service = preference_service

    def create_notification(
        self,
        payload: NotificationCreate,
        *,
        commit: bool = True,
    ) -> NotificationResponse:
        if payload.recipient_type == NotificationRecipientType.USER:
            if payload.company_id is None:
                raise ValueError("company_id is required for staff (user) notifications")
            membership = self.member_repository.get_by_company_and_user(
                payload.company_id,
                payload.recipient_id,
            )
            if membership is None:
                raise PermissionError("Recipient is not a member of the notification company")

        row = Notification(
            recipient_type=payload.recipient_type.value,
            recipient_id=payload.recipient_id,
            company_id=payload.company_id,
            title=payload.title,
            message=payload.message,
            category=payload.category.value,
            priority=payload.priority.value,
            status=NotificationStatus.UNREAD.value,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            metadata_json=dict(payload.metadata or {}),
        )
        created = self.notification_repository.create(row, commit=commit)
        return NotificationResponse.from_orm_notification(created)

    def list_for_user(
        self,
        user: User,
        filters: NotificationFilter | None = None,
    ) -> NotificationListResponse:
        company_ids = self._company_ids_for_user(user)
        if company_ids is None:
            return NotificationListResponse(items=[], total=0, unread_count=0)
        return self._list_for_recipient(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
            filters=filters,
        )

    def summary_for_user(self, user: User) -> NotificationSummaryResponse:
        company_ids = self._company_ids_for_user(user)
        if company_ids is None:
            return NotificationSummaryResponse(total=0, unread_count=0, read_count=0)
        return self._summary_for_recipient(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
        )

    def get_for_user(self, user: User, notification_id: UUID) -> NotificationResponse:
        company_ids = self._require_company_ids_for_user(user)
        row = self.notification_repository.get_owned(
            notification_id=notification_id,
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
        )
        if row is None:
            raise LookupError("Notification not found")
        return NotificationResponse.from_orm_notification(row)

    def mark_for_user(
        self,
        user: User,
        notification_id: UUID,
        status: NotificationStatus,
    ) -> NotificationResponse:
        company_ids = self._require_company_ids_for_user(user)
        row = self.notification_repository.get_owned(
            notification_id=notification_id,
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
        )
        if row is None:
            raise LookupError("Notification not found")
        return self._set_status(row, status)

    def mark_all_read_for_user(self, user: User) -> NotificationMarkAllReadResponse:
        company_ids = self._company_ids_for_user(user)
        if company_ids is None:
            return NotificationMarkAllReadResponse(updated_count=0, unread_count=0)
        updated_count = self.notification_repository.mark_all_read_for_recipient(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
        )
        unread_count = self.notification_repository.count_for_recipient(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user.id,
            company_ids=company_ids,
            status=NotificationStatus.UNREAD,
        )
        return NotificationMarkAllReadResponse(
            updated_count=updated_count,
            unread_count=unread_count,
        )

    def list_for_candidate(
        self,
        candidate: Candidate,
        filters: NotificationFilter | None = None,
    ) -> NotificationListResponse:
        return self._list_for_recipient(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
            filters=filters,
        )

    def summary_for_candidate(self, candidate: Candidate) -> NotificationSummaryResponse:
        return self._summary_for_recipient(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
        )

    def get_for_candidate(self, candidate: Candidate, notification_id: UUID) -> NotificationResponse:
        row = self.notification_repository.get_owned(
            notification_id=notification_id,
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
        )
        if row is None:
            raise LookupError("Notification not found")
        return NotificationResponse.from_orm_notification(row)

    def mark_for_candidate(
        self,
        candidate: Candidate,
        notification_id: UUID,
        status: NotificationStatus,
    ) -> NotificationResponse:
        row = self.notification_repository.get_owned(
            notification_id=notification_id,
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
        )
        if row is None:
            raise LookupError("Notification not found")
        return self._set_status(row, status)

    def mark_all_read_for_candidate(self, candidate: Candidate) -> NotificationMarkAllReadResponse:
        updated_count = self.notification_repository.mark_all_read_for_recipient(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
        )
        unread_count = self.notification_repository.count_for_recipient(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate.id,
            company_ids=None,
            status=NotificationStatus.UNREAD,
        )
        return NotificationMarkAllReadResponse(
            updated_count=updated_count,
            unread_count=unread_count,
        )

    def list_notifications(self, filters: NotificationFilter | None = None) -> NotificationListResponse:
        """Compatibility shim for activity timeline — unscoped calls return empty."""
        _ = filters
        return NotificationListResponse(items=[], total=0, unread_count=0)

    def _company_ids_for_user(self, user: User) -> list[UUID] | None:
        company_ids = self.member_repository.list_company_ids_for_user(user.id)
        if not company_ids:
            return None
        return company_ids

    def _require_company_ids_for_user(self, user: User) -> list[UUID]:
        company_ids = self._company_ids_for_user(user)
        if company_ids is None:
            raise LookupError("Notification not found")
        return company_ids

    def _summary_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None,
    ) -> NotificationSummaryResponse:
        # Fetch unread/total via list path so in-app preference filtering stays consistent.
        listed = self._list_for_recipient(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_ids=company_ids,
            filters=NotificationFilter(limit=500, offset=0),
        )
        unread_count = sum(1 for item in listed.items if item.status == NotificationStatus.UNREAD)
        total = listed.total
        return NotificationSummaryResponse(
            total=total,
            unread_count=unread_count,
            read_count=max(total - unread_count, 0),
        )

    def _list_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_ids: list[UUID] | None,
        filters: NotificationFilter | None,
    ) -> NotificationListResponse:
        query = filters or NotificationFilter()
        # Over-fetch when preference filtering may drop rows, then page in-memory.
        fetch_limit = min(max(query.limit + query.offset, query.limit) * 3, 500)
        fetch_filters = NotificationFilter(
            category=query.category,
            priority=query.priority,
            status=query.status,
            created_after=query.created_after,
            created_before=query.created_before,
            limit=fetch_limit,
            offset=0,
        )
        raw_items = self.notification_repository.list_for_recipient(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_ids=company_ids,
            filters=fetch_filters,
        )
        responses = [
            NotificationResponse.from_orm_notification(item) for item in raw_items
        ]
        visible = [
            item
            for item in responses
            if self._is_in_app_visible(
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                company_id=item.company_id,
                category=item.category,
            )
        ]
        total = len(visible)
        page = visible[query.offset : query.offset + query.limit]
        unread_count = sum(1 for item in visible if item.status == NotificationStatus.UNREAD)
        return NotificationListResponse(
            items=page,
            total=total,
            unread_count=unread_count,
        )

    def _is_in_app_visible(
        self,
        *,
        recipient_type: NotificationRecipientType,
        recipient_id: UUID,
        company_id: UUID | None,
        category: Any,
    ) -> bool:
        if self.preference_service is None:
            return True
        return bool(
            self.preference_service.is_in_app_allowed(
                recipient_type=recipient_type,
                recipient_id=recipient_id,
                company_id=company_id,
                category=category,
            )
        )

    def _set_status(self, row: Notification, status: NotificationStatus) -> NotificationResponse:
        if row.status == status.value:
            return NotificationResponse.from_orm_notification(row)

        now = datetime.now(timezone.utc)
        updates: dict[str, object] = {
            "status": status.value,
            "updated_at": now,
        }
        if status == NotificationStatus.READ:
            updates["read_at"] = now
        else:
            updates["read_at"] = None
        updated = self.notification_repository.update(row, updates)
        return NotificationResponse.from_orm_notification(updated)
