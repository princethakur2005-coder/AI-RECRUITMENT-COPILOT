"""Notification preference domain service — ownership from auth principals only."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.notification import (
    MANDATORY_NOTIFICATION_CATEGORIES,
    NotificationCategory,
    NotificationRecipientType,
)
from app.models.candidate import Candidate
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.notification_preference import NotificationPreferenceRepository
from app.schemas.notification_preference import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)


class NotificationPreferenceService:
    """Default-driven channel preferences for staff and candidates."""

    def __init__(
        self,
        preference_repository: NotificationPreferenceRepository,
        member_repository: CompanyMemberRepository,
    ) -> None:
        self.preference_repository = preference_repository
        self.member_repository = member_repository

    def get_for_user(self, user: User) -> NotificationPreferenceResponse:
        membership = self._require_active_membership(user)
        row = self.preference_repository.get_for_staff(
            user_id=user.id,
            company_id=membership.company_id,
        )
        if row is None:
            return NotificationPreferenceResponse.defaults()
        return NotificationPreferenceResponse.from_orm_row(row)

    def update_for_user(
        self,
        user: User,
        payload: NotificationPreferenceUpdate,
    ) -> NotificationPreferenceResponse:
        membership = self._require_active_membership(user)
        row = self.preference_repository.get_or_create_for_staff(
            user_id=user.id,
            company_id=membership.company_id,
            commit=False,
        )
        updated = self._apply_update(row, payload)
        return NotificationPreferenceResponse.from_orm_row(updated)

    def get_for_candidate(self, candidate: Candidate) -> NotificationPreferenceResponse:
        row = self.preference_repository.get_for_candidate(candidate_id=candidate.id)
        if row is None:
            return NotificationPreferenceResponse.defaults()
        return NotificationPreferenceResponse.from_orm_row(row)

    def update_for_candidate(
        self,
        candidate: Candidate,
        payload: NotificationPreferenceUpdate,
    ) -> NotificationPreferenceResponse:
        row = self.preference_repository.get_or_create_for_candidate(
            candidate_id=candidate.id,
            commit=False,
        )
        updated = self._apply_update(row, payload)
        return NotificationPreferenceResponse.from_orm_row(updated)

    def is_email_allowed(
        self,
        *,
        recipient_type: NotificationRecipientType | str,
        recipient_id: UUID,
        company_id: UUID | None,
        category: NotificationCategory | str,
    ) -> bool:
        return self._channel_allowed(
            channel="email",
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_id=company_id,
            category=category,
        )

    def is_in_app_allowed(
        self,
        *,
        recipient_type: NotificationRecipientType | str,
        recipient_id: UUID,
        company_id: UUID | None,
        category: NotificationCategory | str,
    ) -> bool:
        return self._channel_allowed(
            channel="in_app",
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_id=company_id,
            category=category,
        )

    def _channel_allowed(
        self,
        *,
        channel: str,
        recipient_type: NotificationRecipientType | str,
        recipient_id: UUID,
        company_id: UUID | None,
        category: NotificationCategory | str,
    ) -> bool:
        try:
            cat = (
                category
                if isinstance(category, NotificationCategory)
                else NotificationCategory(str(category))
            )
        except ValueError:
            # Unknown category — treat as allowed (producer validation is separate).
            return True

        if cat in MANDATORY_NOTIFICATION_CATEGORIES:
            return True

        row = self.preference_repository.get_for_recipient(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            company_id=company_id,
        )
        if row is None:
            return True

        if channel == "email":
            if not row.email_enabled:
                return False
            return cat.value not in set(row.email_disabled_categories)
        if channel == "in_app":
            if not row.in_app_enabled:
                return False
            return cat.value not in set(row.in_app_disabled_categories)
        return True

    def _apply_update(
        self,
        row: NotificationPreference,
        payload: NotificationPreferenceUpdate,
    ) -> NotificationPreference:
        updates: dict = {"updated_at": datetime.now(timezone.utc)}
        if payload.email_enabled is not None:
            updates["email_enabled"] = payload.email_enabled
        if payload.in_app_enabled is not None:
            updates["in_app_enabled"] = payload.in_app_enabled
        if payload.email_disabled_categories is not None:
            updates["email_disabled_categories_json"] = list(payload.email_disabled_categories)
        if payload.in_app_disabled_categories is not None:
            updates["in_app_disabled_categories_json"] = list(payload.in_app_disabled_categories)
        return self.preference_repository.update(row, updates)

    def _require_active_membership(self, user: User):
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        return membership
