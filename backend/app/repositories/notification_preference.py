"""Notification preference persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.notification import NotificationRecipientType
from app.models.notification_preference import NotificationPreference
from app.repositories.base import BaseRepository


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    def __init__(self, db) -> None:  # noqa: ANN001
        super().__init__(db, NotificationPreference)

    def get_for_staff(self, *, user_id: UUID, company_id: UUID) -> NotificationPreference | None:
        statement = select(NotificationPreference).where(
            NotificationPreference.recipient_type == NotificationRecipientType.USER.value,
            NotificationPreference.recipient_id == user_id,
            NotificationPreference.company_id == company_id,
        )
        return self.db.scalar(statement)

    def get_for_candidate(self, *, candidate_id: UUID) -> NotificationPreference | None:
        statement = select(NotificationPreference).where(
            NotificationPreference.recipient_type == NotificationRecipientType.CANDIDATE.value,
            NotificationPreference.recipient_id == candidate_id,
            NotificationPreference.company_id.is_(None),
        )
        return self.db.scalar(statement)

    def get_for_recipient(
        self,
        *,
        recipient_type: NotificationRecipientType | str,
        recipient_id: UUID,
        company_id: UUID | None,
    ) -> NotificationPreference | None:
        rtype = (
            recipient_type.value
            if isinstance(recipient_type, NotificationRecipientType)
            else str(recipient_type)
        )
        if rtype == NotificationRecipientType.CANDIDATE.value:
            return self.get_for_candidate(candidate_id=recipient_id)
        if company_id is None:
            return None
        return self.get_for_staff(user_id=recipient_id, company_id=company_id)
