"""Webhook configuration and event envelope schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.notification import NotificationEventType
from app.core.webhook import (
    WEBHOOK_API_VERSION,
    WEBHOOK_ELIGIBLE_EVENTS,
    normalize_webhook_event_type,
    sanitize_webhook_payload,
    validate_webhook_endpoint_url,
)


def _validate_event_types(values: list[str]) -> list[str]:
    if not values:
        raise ValueError("At least one event type is required")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        event = normalize_webhook_event_type(raw)
        if event.value in seen:
            continue
        seen.add(event.value)
        normalized.append(event.value)
    return normalized


class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    description: str | None = Field(default=None, max_length=255)
    event_types: list[str] = Field(..., min_length=1)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        # DNS resolution deferred to service (settings-aware allow_http_localhost).
        return value.strip()

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, value: list[str]) -> list[str]:
        return _validate_event_types(value)


class WebhookUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    description: str | None = Field(default=None, max_length=255)
    event_types: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("event_types")
    @classmethod
    def validate_events(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _validate_event_types(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "WebhookUpdate":
        if (
            self.url is None
            and self.description is None
            and self.event_types is None
            and self.metadata is None
        ):
            raise ValueError("At least one field must be provided")
        return self


class WebhookResponse(BaseModel):
    """Public webhook view — never includes signing secret."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    url: str
    description: str | None = None
    is_active: bool
    event_types: list[str]
    secret_hint: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_webhook(cls, row: Any) -> "WebhookResponse":
        return cls(
            id=row.id,
            company_id=row.company_id,
            url=row.url,
            description=row.description,
            is_active=row.is_active,
            event_types=list(row.event_types),
            secret_hint=row.secret_hint or "",
            metadata=dict(row.metadata_json or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class WebhookCreatedResponse(WebhookResponse):
    """Create response — includes plaintext signing secret exactly once."""

    signing_secret: str


class WebhookEventEnvelope(BaseModel):
    """Stable, versioned outbound webhook envelope."""

    event_id: str
    event_type: NotificationEventType
    occurred_at: datetime
    api_version: str = WEBHOOK_API_VERSION.value
    company_id: UUID
    webhook_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type", mode="before")
    @classmethod
    def coerce_event_type(cls, value: Any) -> NotificationEventType:
        return normalize_webhook_event_type(value)

    @field_validator("data")
    @classmethod
    def sanitize_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return sanitize_webhook_payload(value)

    def to_delivery_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
            "api_version": self.api_version,
            "company_id": str(self.company_id),
            "webhook_id": str(self.webhook_id) if self.webhook_id else None,
            "data": sanitize_webhook_payload(self.data),
        }


# Re-export for callers validating against registry.
SUPPORTED_WEBHOOK_EVENTS = sorted(event.value for event in WEBHOOK_ELIGIBLE_EVENTS)


def assert_url_for_settings(url: str, *, allow_http_localhost: bool, resolve_dns: bool) -> str:
    return validate_webhook_endpoint_url(
        url,
        allow_http_localhost=allow_http_localhost,
        resolve_dns=resolve_dns,
    )
