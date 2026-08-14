"""Enterprise audit event contracts and metadata sanitization."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER

AUDIT_ACTOR_USER = PRINCIPAL_USER
AUDIT_ACTOR_CANDIDATE = PRINCIPAL_CANDIDATE
AUDIT_ACTOR_SYSTEM = "system"

AUDIT_READ_ROLES = frozenset({"company_admin", "recruiter", "hiring_manager"})

SENSITIVE_AUDIT_KEYS = frozenset(
    {
        "password",
        "hashed_password",
        "passwd",
        "secret",
        "signing_secret",
        "signing_secret_sealed",
        "credentials",
        "credentials_sealed",
        "token",
        "access_token",
        "refresh_token",
        "jwt",
        "authorization",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "webhook_secret",
        "smtp_password",
        "cookie",
    }
)


class AuditAction(StrEnum):
    APPLICATION_STATUS_CHANGED = "application.status_changed"
    OFFER_CREATED = "offer_created"
    OFFER_REVISED = "offer_revised"
    OFFER_SUPERSEDED = "offer_superseded"
    OFFER_UPDATED = "offer_updated"
    OFFER_SUBMITTED = "offer_submitted"
    OFFER_APPROVED = "offer_approved"
    OFFER_REJECTED = "offer_rejected"
    OFFER_WITHDRAWN = "offer_withdrawn"
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    INTERVIEW_CREATED = "interview.created"
    INTERVIEW_UPDATED = "interview.updated"
    INTERVIEW_DELETED = "interview.deleted"
    WEBHOOK_CREATED = "webhook.created"
    WEBHOOK_UPDATED = "webhook.updated"
    WEBHOOK_ACTIVATED = "webhook.activated"
    WEBHOOK_DEACTIVATED = "webhook.deactivated"
    WEBHOOK_DELETED = "webhook.deleted"
    CALENDAR_INTEGRATION_CREATED = "calendar_integration.created"
    CALENDAR_INTEGRATION_DISABLED = "calendar_integration.disabled"
    CALENDAR_INTEGRATION_DELETED = "calendar_integration.deleted"


class AuditResourceType(StrEnum):
    APPLICATION = "application"
    OFFER = "offer"
    INTERVIEW = "interview"
    WEBHOOK = "webhook"
    CALENDAR_INTEGRATION = "calendar_integration"


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    if normalized in SENSITIVE_AUDIT_KEYS:
        return True
    return normalized.endswith(("_secret", "_token", "_password", "_jwt", "_credentials"))


def sanitize_audit_metadata(value: Any) -> Any:
    """Drop credentials/secrets from nested audit metadata."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                continue
            cleaned[str(key)] = sanitize_audit_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_audit_metadata(item) for item in value]
    return value
