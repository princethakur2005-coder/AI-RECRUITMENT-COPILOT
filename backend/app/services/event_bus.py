from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

try:
    from app.services.audit_service import audit_service
except Exception:  # pragma: no cover
    audit_service = None  # type: ignore[assignment]


EventHandler = Callable[[Dict[str, Any]], None]


class TaskStore:
    """Backward-compatible placeholder for prior task queue behavior."""

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def enqueue(self, task: Dict[str, Any]) -> None:
        self._items.append(dict(task))

    def list_all(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._items]

    def update(self, task_id: str, updates: Dict[str, Any]) -> None:
        for item in self._items:
            if item.get("id") == task_id:
                item.update(dict(updates))

    def list_pending(self) -> List[Dict[str, Any]]:
        return [item for item in self.list_all() if item.get("status") in (None, "queued")]


class EventDispatcher(Protocol):
    def dispatch(self, event: Dict[str, Any], handlers: List[EventHandler]) -> None:
        ...


class InProcessEventDispatcher:
    """Default synchronous event dispatch strategy."""

    def dispatch(self, event: Dict[str, Any], handlers: List[EventHandler]) -> None:
        payload = dict(event.get("payload") or {})
        for handler in handlers:
            handler(payload)


class EventBus:
    """Provider-agnostic in-process domain event bus."""

    def __init__(
        self,
        task_store: Optional[TaskStore] = None,
        dispatcher: Optional[EventDispatcher] = None,
    ) -> None:
        self._handlers: Dict[str, List[Dict[str, Any]]] = {}
        self._task_store = task_store or TaskStore()
        self._dispatcher = dispatcher or InProcessEventDispatcher()
        self._published_events: List[Dict[str, Any]] = []

    def register_handler(self, event_type: str, handler: EventHandler, background: bool = False) -> None:
        self._handlers.setdefault(event_type, []).append({"fn": handler, "background": bool(background)})

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self.register_handler(event_type=event_type, handler=handler, background=False)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        self._handlers[event_type] = [item for item in handlers if item.get("fn") != handler]

    def publish(self, event_type: str, payload: Dict[str, Any], background: bool = False) -> None:
        event = self.publish_event(
            event_type=event_type,
            payload=payload,
            source=payload.get("source") or "event_bus",
            metadata={"background": bool(background)},
        )
        _ = event

    def publish_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc)
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "payload": dict(payload or {}),
            "metadata": dict(metadata or {}),
            "source": source,
            "timestamp": ts.isoformat(),
        }
        self._published_events.append(event)

        handlers = [item.get("fn") for item in self._handlers.get(event_type, []) if callable(item.get("fn"))]

        try:
            if audit_service is not None:
                audit_service.log(
                    actor_id=str(payload.get("actor_id") or "system"),
                    actor_type=str(payload.get("actor_type") or "system"),
                    action=f"event:{event_type}",
                    resource_type=str(payload.get("resource_type") or "system"),
                    resource_id=payload.get("resource_id"),
                    metadata={"event": event},
                    metadata_payload=dict(metadata or {}),
                    entity_type="domain_event",
                    entity_id=event["id"],
                )
        except Exception:
            pass

        try:
            self._dispatcher.dispatch(event=event, handlers=handlers)
        except Exception as exc:
            try:
                if audit_service is not None:
                    audit_service.log(
                        actor_id="system",
                        actor_type="system",
                        action="event_dispatch_error",
                        resource_type="domain_event",
                        resource_id=event["id"],
                        metadata={"error": str(exc), "event_type": event_type},
                    )
            except Exception:
                pass

        return event

    def list_events(
        self,
        *,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for event in self._published_events:
            if event_type and event.get("type") != event_type:
                continue
            if source and event.get("source") != source:
                continue
            ts = str(event.get("timestamp") or "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            results.append(dict(event))

        results.sort(key=lambda item: str(item.get("timestamp") or ""))
        if limit is not None and limit > 0:
            return results[-limit:]
        return results

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        for event in self._published_events:
            if event.get("id") == event_id:
                return dict(event)
        return None


class BackgroundWorker:
    """Backward-compatible no-op worker."""

    def __init__(self, bus: EventBus, poll_interval: float = 2.0) -> None:
        self.bus = bus
        self.poll_interval = poll_interval

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def run(self) -> None:
        return None

    def _process_task(self, task: Dict[str, Any]) -> None:
        _ = task
        return None


# Global bus and worker
_task_store = TaskStore()
event_bus = EventBus(task_store=_task_store)
worker = BackgroundWorker(event_bus)


def register_default_handlers() -> None:
    return None


# Keep compatibility symbol; no implicit worker startup.
