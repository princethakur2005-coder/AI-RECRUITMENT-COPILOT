"""Legacy multi-channel notification queue (JSON file + optional worker).

Production in-app notifications use PostgreSQL ``NotificationService``.
Production email transport uses ``EmailDeliveryService`` / ``email_provider``.

This module remains for older AI-screening enqueue paths. Prefer
``EmailDeliveryService.send`` for new code. Do not treat this queue as the
notification source of truth.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.notification_center")


class NotificationChannel:
    """Base class for notification channels (email, sms, push, etc.)."""

    name = "base"

    def send(self, payload: Dict[str, Any]) -> None:
        raise NotImplementedError()


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, host: str, port: int, username: Optional[str] = None, password: Optional[str] = None, use_tls: bool = True, default_from: Optional[str] = None) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.default_from = default_from

    def send(self, payload: Dict[str, Any]) -> None:
        to = payload.get("to")
        subject = payload.get("subject", "")
        body = payload.get("body", "")
        html = payload.get("html", False)
        frm = payload.get("from") or self.default_from

        if not to or not frm:
            raise ValueError("Email payload missing 'to' or 'from' fields")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = frm
        msg["To"] = to
        if html:
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        # Attempt to send via SMTP
        if not self.host or not self.port:
            raise RuntimeError("SMTP host/port not configured")

        server = smtplib.SMTP(self.host, self.port, timeout=10)
        try:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass


class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: Dict[str, NotificationChannel] = {}

    def register(self, channel: NotificationChannel) -> None:
        self._channels[channel.name] = channel

    def get(self, name: str) -> Optional[NotificationChannel]:
        return self._channels.get(name)


class NotificationQueueStore:
    PATH = os.path.join(os.path.dirname(__file__), "..", "data", "notification_queue.json")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
        if not os.path.exists(self.PATH):
            with open(self.PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def enqueue(self, item: Dict[str, Any]) -> None:
        data = self._load()
        data[item["id"]] = item
        self._save(data)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._load().values())

    def update(self, item_id: str, updates: Dict[str, Any]) -> None:
        data = self._load()
        if item_id in data:
            data[item_id].update(updates)
            self._save(data)

    def delete(self, item_id: str) -> None:
        data = self._load()
        if item_id in data:
            del data[item_id]
            self._save(data)


@dataclass
class NotificationItem:
    id: str
    channel: str
    payload: Dict[str, Any]
    status: str = "queued"  # queued, sending, delivered, failed
    attempts: int = 0
    max_attempts: int = 5
    next_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


class NotificationWorker:
    def __init__(self, registry: ChannelRegistry, store: NotificationQueueStore, poll_interval: float = 5.0) -> None:
        self.registry = registry
        self.store = store
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                now = datetime.utcnow()
                items = self.store.list_all()
                for it in items:
                    if it.get("status") not in ("queued", "failed"):
                        continue
                    next_at = it.get("next_attempt_at")
                    if next_at:
                        if datetime.fromisoformat(next_at) > now:
                            continue

                    # attempt delivery
                    channel_name = it.get("channel")
                    channel = self.registry.get(channel_name)
                    if not channel:
                        self.store.update(it["id"], {"status": "failed", "last_error": f"Channel {channel_name} not found"})
                        continue

                    try:
                        self.store.update(it["id"], {"status": "sending"})
                        channel.send(it.get("payload") or {})
                        self.store.update(it["id"], {"status": "delivered", "delivered_at": datetime.utcnow().isoformat()})
                    except Exception as exc:
                        attempts = (it.get("attempts") or 0) + 1
                        if attempts >= (it.get("max_attempts") or 5):
                            self.store.update(it["id"], {"status": "failed", "attempts": attempts, "last_error": str(exc)})
                        else:
                            backoff = 2 ** attempts
                            next_at = (datetime.utcnow() + timedelta(seconds=backoff)).isoformat()
                            self.store.update(it["id"], {"status": "failed", "attempts": attempts, "next_attempt_at": next_at, "last_error": str(exc)})
            except Exception:
                # swallow to keep worker alive
                pass
            time.sleep(self.poll_interval)


# Public API
_registry = ChannelRegistry()
_store = NotificationQueueStore()
_worker: Optional[NotificationWorker] = None


def register_channel(channel: NotificationChannel) -> None:
    _registry.register(channel)


def ensure_default_email_channel_from_env() -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "0")) if os.getenv("SMTP_PORT") else 0
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    default_from = os.getenv("SMTP_FROM")
    if host and port:
        email_channel = EmailChannel(host=host, port=port, username=user, password=pwd, use_tls=use_tls, default_from=default_from)
        register_channel(email_channel)


def enqueue_notification(channel: str, payload: Dict[str, Any], max_attempts: int = 5) -> str:
    item = NotificationItem(id=str(uuid.uuid4()), channel=channel, payload=payload, max_attempts=max_attempts)
    _store.enqueue(item.to_dict())
    return item.id


def send_email_async(to: str, subject: str, body: str, html: bool = False, frm: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Legacy enqueue helper. New code should use EmailDeliveryService.send()."""
    payload = {"to": to, "subject": subject, "body": body, "html": html, "from": frm}
    if metadata:
        payload["metadata"] = metadata
    return enqueue_notification("email", payload)


def start_worker(poll_interval: float = 5.0) -> None:
    global _worker
    if _worker and _worker._thread and _worker._thread.is_alive():
        return
    _worker = NotificationWorker(_registry, _store, poll_interval=poll_interval)
    _worker.start()


def stop_worker() -> None:
    global _worker
    if _worker:
        _worker.stop()
        _worker = None


# Initialize default channel from environment at import time (safe to call multiple times)
ensure_default_email_channel_from_env()
