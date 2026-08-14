"""Typed contracts for application-level email delivery."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmailDeliveryStatus(StrEnum):
    """Outcome of an email delivery attempt.

    ``DELIVERED`` is the only status that means the provider was invoked successfully.
    ``SKIPPED`` means delivery was intentionally not attempted (disabled / unconfigured).
    ``FAILED`` means the provider was attempted or rejected and did not succeed.
    """

    DELIVERED = "delivered"
    SKIPPED = "skipped"
    FAILED = "failed"


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("Invalid email address")
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        raise ValueError("Invalid email address")
    if any(ch.isspace() for ch in email):
        raise ValueError("Invalid email address")
    return email


class EmailAddress(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(..., min_length=3, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("display_name", mode="before")
    @classmethod
    def empty_name_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class EmailMessage(BaseModel):
    """Provider-agnostic outbound email message."""

    model_config = ConfigDict(str_strip_whitespace=True)

    to: EmailAddress
    subject: str = Field(..., min_length=1, max_length=255)
    body_text: str = Field(..., min_length=1)
    body_html: str | None = None
    reply_to: EmailAddress | None = None
    # Correlation / operational metadata only — never credentials or secrets.
    correlation_id: str | None = Field(default=None, max_length=128)
    notification_id: UUID | None = None
    event_type: str | None = Field(default=None, max_length=64)
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    company_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_sensitive_metadata_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        blocked = {
            "password",
            "hashed_password",
            "token",
            "access_token",
            "refresh_token",
            "jwt",
            "authorization",
            "secret",
            "api_key",
            "smtp_password",
        }
        cleaned: dict[str, Any] = {}
        for key, item in (value or {}).items():
            key_l = str(key).lower()
            if key_l in blocked or any(part in key_l for part in ("password", "token", "secret", "jwt")):
                continue
            cleaned[key] = item
        return cleaned


class EmailDeliveryResult(BaseModel):
    status: EmailDeliveryStatus
    provider: str
    message: str | None = None
    correlation_id: str | None = None
    notification_id: UUID | None = None

    @property
    def delivered(self) -> bool:
        return self.status == EmailDeliveryStatus.DELIVERED

    @property
    def attempted(self) -> bool:
        return self.status in {EmailDeliveryStatus.DELIVERED, EmailDeliveryStatus.FAILED}
