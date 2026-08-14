"""HTTP webhook delivery transport — provider-agnostic boundary."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import httpx

from app.core.config import Settings, get_settings
from app.core.webhook import (
    WEBHOOK_EVENT_ID_HEADER,
    WEBHOOK_EVENT_TYPE_HEADER,
    WEBHOOK_ID_HEADER,
    WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_TIMESTAMP_HEADER,
    sign_webhook_payload,
)

logger = logging.getLogger("app.webhook_delivery")


@dataclass(frozen=True)
class WebhookDeliveryRequest:
    webhook_id: UUID
    url: str
    signing_secret: str
    event_id: str
    event_type: str
    body: bytes
    timestamp: str


@dataclass(frozen=True)
class WebhookDeliveryResult:
    success: bool
    status_code: int | None
    retryable: bool
    duration_ms: int
    error_code: str | None = None
    message: str | None = None


class WebhookHttpTransport(Protocol):
    def post(
        self,
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        """Return (status_code, response_body). Raise on transport errors."""


class HttpxWebhookTransport:
    """Production HTTP transport with strict timeouts and no redirects."""

    def post(
        self,
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[int, bytes]:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(url, content=content, headers=headers)
            return response.status_code, response.content


class WebhookDeliveryService:
    """Signs and POSTs webhook envelopes. Never logs signing secrets."""

    RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        transport: WebhookHttpTransport | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.transport = transport or HttpxWebhookTransport()
        self.settings = settings or get_settings()

    def deliver(self, request: WebhookDeliveryRequest) -> WebhookDeliveryResult:
        signature = sign_webhook_payload(
            secret=request.signing_secret,
            timestamp=request.timestamp,
            body=request.body,
        )
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Recruitment-Copilot-Webhook/1.0",
            WEBHOOK_SIGNATURE_HEADER: signature,
            WEBHOOK_TIMESTAMP_HEADER: request.timestamp,
            WEBHOOK_EVENT_ID_HEADER: request.event_id,
            WEBHOOK_EVENT_TYPE_HEADER: request.event_type,
            WEBHOOK_ID_HEADER: str(request.webhook_id),
        }
        timeout = float(self.settings.WEBHOOK_HTTP_TIMEOUT_SECONDS)
        started = time.perf_counter()

        try:
            status_code, _body = self.transport.post(
                request.url,
                content=request.body,
                headers=headers,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "webhook_delivery_timeout webhook_id=%s event_id=%s duration_ms=%s",
                request.webhook_id,
                request.event_id,
                duration_ms,
            )
            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                retryable=True,
                duration_ms=duration_ms,
                error_code="timeout",
                message="Webhook HTTP request timed out",
            )
        except httpx.HTTPError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "webhook_delivery_transport_error webhook_id=%s event_id=%s error_type=%s duration_ms=%s",
                request.webhook_id,
                request.event_id,
                type(exc).__name__,
                duration_ms,
            )
            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                retryable=True,
                duration_ms=duration_ms,
                error_code="transport_error",
                message=f"Webhook transport error: {type(exc).__name__}",
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "webhook_delivery_unexpected_error webhook_id=%s event_id=%s error_type=%s duration_ms=%s",
                request.webhook_id,
                request.event_id,
                type(exc).__name__,
                duration_ms,
            )
            return WebhookDeliveryResult(
                success=False,
                status_code=None,
                retryable=True,
                duration_ms=duration_ms,
                error_code="unexpected_error",
                message=f"Unexpected webhook error: {type(exc).__name__}",
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        if 200 <= status_code < 300:
            logger.info(
                "webhook_delivery_succeeded webhook_id=%s event_id=%s status=%s duration_ms=%s",
                request.webhook_id,
                request.event_id,
                status_code,
                duration_ms,
            )
            return WebhookDeliveryResult(
                success=True,
                status_code=status_code,
                retryable=False,
                duration_ms=duration_ms,
            )

        retryable = status_code in self.RETRYABLE_STATUS_CODES
        logger.warning(
            "webhook_delivery_http_failure webhook_id=%s event_id=%s status=%s retryable=%s duration_ms=%s",
            request.webhook_id,
            request.event_id,
            status_code,
            retryable,
            duration_ms,
        )
        return WebhookDeliveryResult(
            success=False,
            status_code=status_code,
            retryable=retryable,
            duration_ms=duration_ms,
            error_code="http_error",
            message=f"Webhook endpoint returned HTTP {status_code}",
        )
