from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


class AuditEvent(dict):
    pass


class AuditStore:
    """Append-only audit log with a simple index for candidate timelines.

    - Writes are append-only to a JSONL file for traceability.
    - Maintains a small index mapping candidate_id -> list of event ids (for quick timeline retrieval).
    """

    LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit_log.jsonl")
    INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit_index.json")

    def __init__(self) -> None:
        os.makedirs(os.path.dirname(self.LOG_PATH), exist_ok=True)
        # Ensure files exist
        open(self.LOG_PATH, "a", encoding="utf-8").close()
        if not os.path.exists(self.INDEX_PATH):
            with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                json.dump({}, fh)

        self._lock = threading.Lock()

    def append_event(self, event: Dict[str, Any]) -> None:
        """Append an event to the log and update index atomically within the process."""
        with self._lock:
            # append to log
            with open(self.LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")

            # update index for candidate if present
            candidate_id = None
            # resource_type might be 'candidate' or metadata may include candidate_id
            if event.get("resource_type") == "candidate":
                candidate_id = event.get("resource_id")
            else:
                md = event.get("metadata") or {}
                candidate_id = md.get("candidate_id")

            if candidate_id:
                try:
                    with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                        idx = json.load(fh)
                except Exception:
                    idx = {}

                lst = idx.get(candidate_id) or []
                lst.append(event["id"])
                idx[candidate_id] = lst
                with open(self.INDEX_PATH, "w", encoding="utf-8") as fh:
                    json.dump(idx, fh, ensure_ascii=False, indent=2)

    def iter_events(self) -> Iterable[Dict[str, Any]]:
        with open(self.LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        for ev in self.iter_events():
            if ev.get("id") == event_id:
                return ev
        return None

    def get_candidate_event_ids(self, candidate_id: str) -> List[str]:
        try:
            with open(self.INDEX_PATH, "r", encoding="utf-8") as fh:
                idx = json.load(fh)
            return idx.get(candidate_id, [])
        except Exception:
            return []


class AuditService:
    """High-level audit API used by other services.

    Use `log` to record actions. Provides `get_candidate_timeline` for chronological views.
    """

    def __init__(self, store: Optional[AuditStore] = None) -> None:
        self.store = store or AuditStore()

    def log(
        self,
        actor_id: str,
        actor_type: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "info",
        correlation_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        current_state: Optional[Dict[str, Any]] = None,
        metadata_payload: Optional[Dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> str:
        """Record an audit event.

        Returns the event id.
        """
        event_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"
        merged_metadata = dict(metadata or {})
        if metadata_payload:
            merged_metadata["payload"] = dict(metadata_payload)

        resolved_entity_type = entity_type or resource_type
        resolved_entity_id = entity_id or resource_id

        ev: Dict[str, Any] = {
            "id": event_id,
            "timestamp": ts,
            "actor_id": actor_id,
            "actor_type": actor_type,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "entity_type": resolved_entity_type,
            "entity_id": resolved_entity_id,
            "previous_state": previous_state or {},
            "current_state": current_state or {},
            "metadata": merged_metadata,
            "level": level,
            "correlation_id": correlation_id,
        }
        # Write append-only
        self.store.append_event(ev)
        return event_id

    def create_event(
        self,
        actor_id: str,
        actor_type: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        current_state: Optional[Dict[str, Any]] = None,
        metadata_payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "info",
        correlation_id: Optional[str] = None,
    ) -> str:
        return self.log(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource_type=entity_type,
            resource_id=entity_id,
            metadata=metadata,
            level=level,
            correlation_id=correlation_id,
            previous_state=previous_state,
            current_state=current_state,
            metadata_payload=metadata_payload,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def get_candidate_timeline(self, candidate_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return chronological timeline for a given candidate.

        Uses the index for performance; falls back to scanning log if index missing.
        """
        ids = self.store.get_candidate_event_ids(candidate_id)
        events: List[Dict[str, Any]] = []
        if ids:
            for eid in ids:
                ev = self.store.get_event_by_id(eid)
                if ev:
                    events.append(ev)
        else:
            # fallback: scan whole log and filter
            for ev in self.store.iter_events():
                if ev.get("resource_type") == "candidate" and ev.get("resource_id") == candidate_id:
                    events.append(ev)
                else:
                    md = ev.get("metadata") or {}
                    if md.get("candidate_id") == candidate_id:
                        events.append(ev)

        # sort chronological
        events.sort(key=lambda e: e.get("timestamp") or "")
        if limit:
            return events[-limit:]
        return events

    def query(self, *, actor_id: Optional[str] = None, resource_type: Optional[str] = None, action: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.filter_events(actor_id=actor_id, resource_type=resource_type, action=action)

    def filter_events(
        self,
        *,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        level: Optional[str] = None,
        correlation_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for ev in self.store.iter_events():
            if actor_id and ev.get("actor_id") != actor_id:
                continue
            if actor_type and ev.get("actor_type") != actor_type:
                continue
            if resource_type and ev.get("resource_type") != resource_type:
                continue
            if resource_id and ev.get("resource_id") != resource_id:
                continue
            if entity_type and ev.get("entity_type") != entity_type:
                continue
            if entity_id and ev.get("entity_id") != entity_id:
                continue
            if action and ev.get("action") != action:
                continue
            if level and ev.get("level") != level:
                continue
            if correlation_id and ev.get("correlation_id") != correlation_id:
                continue

            timestamp = str(ev.get("timestamp") or "")
            if since and timestamp and timestamp < since:
                continue
            if until and timestamp and timestamp > until:
                continue

            results.append(ev)

        results.sort(key=lambda item: item.get("timestamp") or "")
        if limit is not None and limit > 0:
            return results[-limit:]
        return results

    def get_entity_history(self, entity_type: str, entity_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.filter_events(entity_type=entity_type, entity_id=entity_id, limit=limit)


# Single global instance for convenience
audit_service = AuditService()
