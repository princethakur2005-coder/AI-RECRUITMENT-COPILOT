"""Application-level email delivery boundary.

Domain services and notification producers depend on this service — never on SMTP
or provider-specific clients directly.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.schemas.email_delivery import EmailDeliveryResult, EmailDeliveryStatus, EmailMessage
from app.services.email_provider import EmailProvider, build_email_provider

logger = logging.getLogger("app.email_delivery")


class EmailDeliveryService:
    """Single application email delivery abstraction (provider-agnostic)."""

    def __init__(
        self,
        provider: EmailProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or build_email_provider(self.settings)

    @property
    def is_enabled(self) -> bool:
        return bool(self.settings.EMAIL_DELIVERY_ENABLED) and self.provider.name != "null"

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Send through the configured provider. Never raises for transport failures."""
        try:
            result = self.provider.send(message)
        except Exception as exc:
            logger.exception(
                "email_provider_raised event_type=%s notification_id=%s error_type=%s",
                message.event_type,
                message.notification_id,
                type(exc).__name__,
            )
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=getattr(self.provider, "name", "unknown"),
                message=f"Provider raised: {type(exc).__name__}",
                correlation_id=message.correlation_id,
                notification_id=message.notification_id,
            )

        if result.status == EmailDeliveryStatus.DELIVERED and not result.delivered:
            # Defensive: never allow inconsistent success claims.
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=result.provider,
                message="Inconsistent delivery result",
                correlation_id=message.correlation_id,
                notification_id=message.notification_id,
            )
        return result
