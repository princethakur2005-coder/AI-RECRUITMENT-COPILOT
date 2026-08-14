"""Enqueue durable webhook delivery jobs for subscribed company endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5, UUID as UuidType

from app.core.durable_job import DurableJobType
from app.core.notification import NotificationEventType
from app.core.webhook import (
    WEBHOOK_API_VERSION,
    WEBHOOK_ELIGIBLE_EVENTS,
    normalize_webhook_event_type,
    sanitize_webhook_payload,
)
from app.repositories.webhook import WebhookRepository
from app.schemas.durable_job import DurableJobSubmit
from app.schemas.webhook import WebhookEventEnvelope
from app.services.durable_job_service import DurableJobService

logger = logging.getLogger("app.webhook_events")

# Stable namespace for deterministic event IDs (idempotency).
_EVENT_NAMESPACE = UuidType("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class WebhookEventDispatcher:
    """Maps domain events → durable webhook.delivery jobs (no HTTP in-process)."""

    def __init__(
        self,
        webhook_repository: WebhookRepository,
        job_service: DurableJobService | None = None,
    ) -> None:
        self.webhook_repository = webhook_repository
        self.job_service = job_service

    def dispatch(
        self,
        *,
        company_id: UUID,
        event_type: str | NotificationEventType,
        data: dict[str, Any],
        occurred_at: datetime | None = None,
        event_id: str | None = None,
        entity_key: str | None = None,
    ) -> int:
        """Enqueue delivery jobs for matching active webhooks. Returns job count."""
        try:
            event = normalize_webhook_event_type(event_type)
        except ValueError:
            return 0

        if event not in WEBHOOK_ELIGIBLE_EVENTS:
            return 0

        if self.job_service is None:
            logger.warning(
                "webhook_dispatch_skipped_no_job_service company_id=%s event_type=%s",
                company_id,
                event.value,
            )
            return 0

        when = occurred_at or datetime.now(timezone.utc)
        safe_data = sanitize_webhook_payload(data)
        resolved_event_id = event_id or self._build_event_id(
            company_id=company_id,
            event_type=event.value,
            entity_key=entity_key or "",
            data=safe_data,
            occurred_at=when,
        )

        webhooks = self.webhook_repository.list_active_for_event(company_id, event.value)
        enqueued = 0
        for webhook in webhooks:
            envelope = WebhookEventEnvelope(
                event_id=resolved_event_id,
                event_type=event,
                occurred_at=when,
                api_version=WEBHOOK_API_VERSION.value,
                company_id=company_id,
                webhook_id=webhook.id,
                data=safe_data,
            )
            try:
                self.job_service.submit(
                    DurableJobSubmit(
                        job_type=DurableJobType.WEBHOOK_DELIVERY,
                        payload={
                            "webhook_id": str(webhook.id),
                            "event_id": resolved_event_id,
                            "event_type": event.value,
                            "envelope": envelope.to_delivery_dict(),
                        },
                        idempotency_key=f"webhook:{webhook.id}:{resolved_event_id}",
                        correlation_id=resolved_event_id,
                        company_id=company_id,
                    )
                )
                enqueued += 1
            except Exception:
                logger.exception(
                    "webhook_job_enqueue_failed webhook_id=%s event_id=%s event_type=%s",
                    webhook.id,
                    resolved_event_id,
                    event.value,
                )
        return enqueued

    @staticmethod
    def _build_event_id(
        *,
        company_id: UUID,
        event_type: str,
        entity_key: str,
        data: dict[str, Any],
        occurred_at: datetime,
    ) -> str:
        fingerprint = "|".join(
            [
                str(company_id),
                event_type,
                entity_key,
                str(data.get("status") or ""),
                str(data.get("previous_status") or ""),
                str(data.get("offer_status") or ""),
                # Bucket to second so retries of same mutation stay idempotent.
                occurred_at.replace(microsecond=0).isoformat(),
            ]
        )
        return str(uuid5(_EVENT_NAMESPACE, fingerprint))
