"""Provider abstraction for outbound email transport."""

from __future__ import annotations

from abc import ABC, abstractmethod
from email.message import EmailMessage as StdlibEmailMessage
from email.utils import formataddr
import logging
import smtplib

from app.core.config import Settings, get_settings
from app.schemas.email_delivery import EmailDeliveryResult, EmailDeliveryStatus, EmailMessage

logger = logging.getLogger("app.email_provider")


class EmailProvider(ABC):
    """Transport-only provider. Domain services must not depend on concrete providers."""

    name: str = "base"

    @abstractmethod
    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        raise NotImplementedError


class NullEmailProvider(EmailProvider):
    """No-op provider used when delivery is disabled or SMTP is not configured."""

    name = "null"

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        logger.info(
            "email_skipped provider=null event_type=%s notification_id=%s correlation_id=%s",
            message.event_type,
            message.notification_id,
            message.correlation_id,
        )
        return EmailDeliveryResult(
            status=EmailDeliveryStatus.SKIPPED,
            provider=self.name,
            message="Email delivery disabled or SMTP not configured",
            correlation_id=message.correlation_id,
            notification_id=message.notification_id,
        )


class SmtpEmailProvider(EmailProvider):
    """stdlib SMTP provider — credentials loaded from Settings only."""

    name = "smtp"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        host = (self.settings.SMTP_HOST or "").strip()
        port = int(self.settings.SMTP_PORT or 0)
        from_email = (self.settings.smtp_from_email_effective or "").strip()
        if not host or not port or not from_email:
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=self.name,
                message="SMTP host/port/from are not fully configured",
                correlation_id=message.correlation_id,
                notification_id=message.notification_id,
            )

        from_name = (self.settings.SMTP_FROM_NAME or "").strip() or None
        msg = StdlibEmailMessage()
        msg["Subject"] = message.subject
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        msg["To"] = (
            formataddr((message.to.display_name, message.to.email))
            if message.to.display_name
            else message.to.email
        )

        reply_to = message.reply_to
        if reply_to is None and self.settings.SMTP_REPLY_TO:
            reply_to_email = self.settings.SMTP_REPLY_TO.strip()
            if reply_to_email:
                msg["Reply-To"] = reply_to_email
        elif reply_to is not None:
            msg["Reply-To"] = (
                formataddr((reply_to.display_name, reply_to.email))
                if reply_to.display_name
                else reply_to.email
            )

        if message.correlation_id:
            msg["X-Correlation-Id"] = message.correlation_id
        if message.notification_id is not None:
            msg["X-Notification-Id"] = str(message.notification_id)

        if message.body_html:
            msg.set_content(message.body_text)
            msg.add_alternative(message.body_html, subtype="html")
        else:
            msg.set_content(message.body_text)

        try:
            timeout = int(self.settings.SMTP_TIMEOUT_SECONDS or 10)
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                if self.settings.SMTP_USE_TLS:
                    server.starttls()
                username = (self.settings.smtp_username_effective or "").strip()
                password = self.settings.SMTP_PASSWORD or ""
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        except Exception as exc:
            # Do not log credentials or full message bodies with PII beyond operational ids.
            logger.exception(
                "email_failed provider=smtp event_type=%s notification_id=%s correlation_id=%s error_type=%s",
                message.event_type,
                message.notification_id,
                message.correlation_id,
                type(exc).__name__,
            )
            return EmailDeliveryResult(
                status=EmailDeliveryStatus.FAILED,
                provider=self.name,
                message=f"SMTP send failed: {type(exc).__name__}",
                correlation_id=message.correlation_id,
                notification_id=message.notification_id,
            )

        logger.info(
            "email_delivered provider=smtp event_type=%s notification_id=%s correlation_id=%s",
            message.event_type,
            message.notification_id,
            message.correlation_id,
        )
        return EmailDeliveryResult(
            status=EmailDeliveryStatus.DELIVERED,
            provider=self.name,
            message="Message accepted by SMTP server",
            correlation_id=message.correlation_id,
            notification_id=message.notification_id,
        )


def build_email_provider(settings: Settings | None = None) -> EmailProvider:
    """Factory: SMTP when enabled+configured, otherwise null (never claims delivery)."""
    cfg = settings or get_settings()
    if not cfg.EMAIL_DELIVERY_ENABLED:
        return NullEmailProvider()
    host = (cfg.SMTP_HOST or "").strip()
    from_email = (cfg.smtp_from_email_effective or "").strip()
    if not host or not cfg.SMTP_PORT or not from_email:
        return NullEmailProvider()
    return SmtpEmailProvider(cfg)
