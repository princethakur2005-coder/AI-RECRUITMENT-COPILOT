"""Execute webhook delivery durable jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.durable_job import JobExecutionError
from app.core.secret_box import unseal_secret
from app.models.durable_job import DurableJob
from app.repositories.webhook import WebhookRepository
from app.services.webhook_delivery import WebhookDeliveryRequest, WebhookDeliveryService


class WebhookDeliveryJobHandler:
    """Loads webhook config + secret server-side; never trusts job payload secrets."""

    def __init__(
        self,
        db: Session,
        *,
        delivery_service: WebhookDeliveryService | None = None,
    ) -> None:
        self.db = db
        self.webhook_repository = WebhookRepository(db)
        self.delivery_service = delivery_service or WebhookDeliveryService()
        self.settings = get_settings()

    def execute(self, job: DurableJob) -> None:
        payload = job.payload or {}
        webhook_id_raw = payload.get("webhook_id")
        envelope = payload.get("envelope")
        if not webhook_id_raw or not isinstance(envelope, dict):
            raise JobExecutionError(
                "Webhook delivery job missing webhook_id or envelope",
                retryable=False,
                error_code="invalid_payload",
            )

        try:
            webhook_id = UUID(str(webhook_id_raw))
        except ValueError as exc:
            raise JobExecutionError(
                "Invalid webhook_id in job payload",
                retryable=False,
                error_code="invalid_payload",
            ) from exc

        webhook = self.webhook_repository.get_by_id(webhook_id)
        if webhook is None:
            raise JobExecutionError(
                "Webhook configuration not found",
                retryable=False,
                error_code="webhook_not_found",
            )
        if not webhook.is_active:
            # Disabled after enqueue — treat as successful skip.
            return
        if job.company_id is not None and webhook.company_id != job.company_id:
            raise JobExecutionError(
                "Webhook company mismatch",
                retryable=False,
                error_code="tenant_mismatch",
            )

        try:
            signing_secret = unseal_secret(
                webhook.signing_secret_sealed,
                self.settings.SECRET_KEY,
            )
        except ValueError as exc:
            raise JobExecutionError(
                "Webhook signing secret unavailable",
                retryable=False,
                error_code="secret_unseal_failed",
            ) from exc

        # Ensure envelope webhook_id matches claimed config.
        delivery_envelope = dict(envelope)
        delivery_envelope["webhook_id"] = str(webhook.id)
        body = json.dumps(delivery_envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        result = self.delivery_service.deliver(
            WebhookDeliveryRequest(
                webhook_id=webhook.id,
                url=webhook.url,
                signing_secret=signing_secret,
                event_id=str(delivery_envelope.get("event_id") or payload.get("event_id") or ""),
                event_type=str(delivery_envelope.get("event_type") or payload.get("event_type") or ""),
                body=body,
                timestamp=timestamp,
            )
        )

        # Persist operational metadata on the job row without committing secrets.
        meta = dict(job.payload_json or {})
        meta["last_delivery"] = {
            "status_code": result.status_code,
            "duration_ms": result.duration_ms,
            "success": result.success,
            "error_code": result.error_code,
            "message": result.message,
            "delivered_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        job.payload_json = meta

        if result.success:
            return

        raise JobExecutionError(
            result.message or "Webhook delivery failed",
            retryable=result.retryable,
            error_code=result.error_code or "webhook_delivery_failed",
        )
