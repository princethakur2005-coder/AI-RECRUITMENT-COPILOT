"""Notification preference schemas — no secrets, no client-owned identity."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.notification import (
    MANDATORY_NOTIFICATION_CATEGORIES,
    PREFERENCE_CONFIGURABLE_CATEGORIES,
    NotificationCategory,
    NotificationRecipientType,
)


def _normalize_category_list(values: list[str] | None) -> list[str]:
    if values is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        category = NotificationCategory(str(raw).strip().lower())
        if category in MANDATORY_NOTIFICATION_CATEGORIES:
            raise ValueError(
                f"Category '{category.value}' is mandatory and cannot be disabled"
            )
        if category not in PREFERENCE_CONFIGURABLE_CATEGORIES:
            raise ValueError(f"Unsupported preference category: {category.value}")
        if category.value in seen:
            continue
        seen.add(category.value)
        normalized.append(category.value)
    return normalized


class NotificationPreferenceResponse(BaseModel):
    """Effective preferences for the authenticated recipient (defaults applied)."""

    model_config = ConfigDict(from_attributes=True)

    email_enabled: bool = True
    in_app_enabled: bool = True
    email_disabled_categories: list[str] = Field(default_factory=list)
    in_app_disabled_categories: list[str] = Field(default_factory=list)
    mandatory_categories: list[str] = Field(
        default_factory=lambda: sorted(c.value for c in MANDATORY_NOTIFICATION_CATEGORIES)
    )
    configurable_categories: list[str] = Field(
        default_factory=lambda: sorted(c.value for c in PREFERENCE_CONFIGURABLE_CATEGORIES)
    )

    @classmethod
    def defaults(cls) -> "NotificationPreferenceResponse":
        return cls()

    @classmethod
    def from_orm_row(cls, row: Any) -> "NotificationPreferenceResponse":
        return cls(
            email_enabled=bool(row.email_enabled),
            in_app_enabled=bool(row.in_app_enabled),
            email_disabled_categories=list(row.email_disabled_categories),
            in_app_disabled_categories=list(row.in_app_disabled_categories),
        )


class NotificationPreferenceUpdate(BaseModel):
    """PATCH body — only provided fields are applied."""

    email_enabled: bool | None = None
    in_app_enabled: bool | None = None
    email_disabled_categories: list[str] | None = None
    in_app_disabled_categories: list[str] | None = None

    @field_validator("email_disabled_categories", "in_app_disabled_categories")
    @classmethod
    def validate_categories(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_category_list(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "NotificationPreferenceUpdate":
        if (
            self.email_enabled is None
            and self.in_app_enabled is None
            and self.email_disabled_categories is None
            and self.in_app_disabled_categories is None
        ):
            raise ValueError("At least one preference field must be provided")
        return self


class PreferenceDecisionContext(BaseModel):
    """Internal delivery decision input — never a public API body."""

    recipient_type: NotificationRecipientType
    recipient_id: UUID
    company_id: UUID | None = None
    category: NotificationCategory | str
