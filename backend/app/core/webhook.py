"""Webhook domain contracts — subscriptions, signing, and SSRF-safe URL rules."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
from enum import StrEnum
from urllib.parse import urlparse

from app.core.notification import NotificationEventType


class WebhookApiVersion(StrEnum):
    """Versioned webhook envelope contract. Do not silently change meaning."""

    V2026_08_13 = "2026-08-13"


WEBHOOK_API_VERSION = WebhookApiVersion.V2026_08_13

# First-pack webhook-eligible domain events (reuse NotificationEventType values).
WEBHOOK_ELIGIBLE_EVENTS: frozenset[NotificationEventType] = frozenset(
    {
        NotificationEventType.APPLICATION_STATUS_CHANGED,
        NotificationEventType.INTERVIEW_SCHEDULED,
        NotificationEventType.OFFER_CREATED,
        NotificationEventType.OFFER_ACCEPTED,
        NotificationEventType.OFFER_DECLINED,
    }
)

WEBHOOK_SIGNATURE_HEADER = "X-Webhook-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-Webhook-Timestamp"
WEBHOOK_EVENT_ID_HEADER = "X-Webhook-Event-Id"
WEBHOOK_EVENT_TYPE_HEADER = "X-Webhook-Event-Type"
WEBHOOK_ID_HEADER = "X-Webhook-Id"
WEBHOOK_SIGNATURE_PREFIX = "v1="

# Privacy-safe keys allowed in outbound webhook data payloads.
WEBHOOK_SAFE_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "application_id",
        "candidate_id",
        "company_id",
        "interview_id",
        "interview_type",
        "job_id",
        "job_title",
        "offer_id",
        "offer_status",
        "previous_status",
        "status",
    }
)


def normalize_webhook_event_type(value: str | NotificationEventType) -> NotificationEventType:
    event = value if isinstance(value, NotificationEventType) else NotificationEventType(str(value))
    if event not in WEBHOOK_ELIGIBLE_EVENTS:
        raise ValueError(f"Unsupported webhook event type: {event.value}")
    return event


def sanitize_webhook_payload(data: dict) -> dict:
    """Strip anything outside the explicit webhook data contract."""
    cleaned: dict = {}
    for key, value in (data or {}).items():
        key_s = str(key)
        key_l = key_s.lower()
        if key_s not in WEBHOOK_SAFE_PAYLOAD_KEYS:
            continue
        if any(part in key_l for part in ("password", "token", "secret", "jwt", "note", "ai_")):
            continue
        cleaned[key_s] = value
    return cleaned


def sign_webhook_payload(*, secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over ``{timestamp}.{body}`` — Stripe-style v1 signature."""
    signed_payload = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"{WEBHOOK_SIGNATURE_PREFIX}{digest}"


def verify_webhook_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    signature_header: str,
) -> bool:
    expected = sign_webhook_payload(secret=secret, timestamp=timestamp, body=body)
    provided = (signature_header or "").strip()
    return hmac.compare_digest(expected, provided)


def validate_webhook_endpoint_url(
    url: str,
    *,
    allow_http_localhost: bool = False,
    resolve_dns: bool = True,
) -> str:
    """Validate endpoint URL and reject private/metadata targets (SSRF guard)."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Webhook URL is required")
    if len(raw) > 2048:
        raise ValueError("Webhook URL is too long")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Webhook URL must include a hostname")

    if scheme == "https":
        pass
    elif scheme == "http" and allow_http_localhost and host in {"localhost", "127.0.0.1", "::1"}:
        pass
    else:
        raise ValueError("Webhook URL must use https")

    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not include credentials")

    if host in {"metadata.google.internal", "metadata", "metadata.google"}:
        raise ValueError("Webhook URL target is not allowed")

    if resolve_dns:
        _assert_host_not_private(host)
    elif _is_literal_private_host(host):
        raise ValueError("Webhook URL must not target private or link-local addresses")

    return raw


def _is_literal_private_host(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _assert_host_not_private(host: str) -> None:
    if _is_literal_private_host(host):
        raise ValueError("Webhook URL must not target private or link-local addresses")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError("Webhook URL hostname could not be resolved") from exc
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise ValueError("Webhook URL must not resolve to a private or link-local address")
