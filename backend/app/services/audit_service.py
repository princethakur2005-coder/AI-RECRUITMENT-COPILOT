from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.audit import AUDIT_READ_ROLES, sanitize_audit_metadata
from app.core.logging import get_request_id
from app.models.audit_event import AuditEvent
from app.models.user import User
from app.repositories.audit_event import AuditEventRepository
from app.repositories.company_member import CompanyMemberRepository

logger = logging.getLogger("app.audit")


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

    JSONL remains available for legacy timeline/search consumers. PostgreSQL is
    the enterprise source of truth when a repository is bound.
    """

    def __init__(
        self,
        store: Optional[AuditStore] = None,
        repository: AuditEventRepository | None = None,
        member_repository: CompanyMemberRepository | None = None,
    ) -> None:
        self.store = store or AuditStore()
        self.repository = repository
        self.member_repository = member_repository

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
        ts = datetime.now(timezone.utc).isoformat()
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

    def _resolve_request_id(self, request_id: str | None = None) -> str | None:
        resolved = request_id if request_id is not None else get_request_id()
        if resolved in (None, "", "-"):
            return None
        return str(resolved)[:128]

    def persist(
        self,
        *,
        company_id: UUID,
        actor_type: str,
        action: str,
        resource_type: str,
        actor_id: UUID | str | None = None,
        resource_id: UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        commit: bool = True,
    ) -> AuditEvent | None:
        """Append a tenant-scoped PostgreSQL audit row. Never mutates existing rows."""
        if self.repository is None:
            return None
        actor_uuid = _as_uuid(actor_id)
        resource_uuid = _as_uuid(resource_id)
        event = AuditEvent(
            company_id=company_id,
            actor_type=str(actor_type),
            actor_id=actor_uuid,
            action=str(action),
            resource_type=str(resource_type),
            resource_id=resource_uuid,
            request_id=self._resolve_request_id(request_id),
            metadata_json=sanitize_audit_metadata(dict(metadata or {})),
        )
        return self.repository.append(event, commit=commit)

    def list_for_user(
        self,
        user: User,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditEvent], int]:
        if self.repository is None or self.member_repository is None:
            raise PermissionError("Persistent audit query is unavailable")
        membership = self.member_repository.get_by_user_id(user.id)
        if membership is None or not membership.is_active:
            raise PermissionError("Active company membership required")
        if membership.role not in AUDIT_READ_ROLES:
            raise PermissionError("Insufficient permissions for audit logs")
        company_id = membership.company_id
        items = self.repository.list_for_company(
            company_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            actor_type=actor_type,
            created_after=created_after,
            created_before=created_before,
            offset=offset,
            limit=limit,
        )
        total = self.repository.count_for_company(
            company_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            actor_type=actor_type,
            created_after=created_after,
            created_before=created_before,
        )
        return items, total


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def emit_audit(
    db: Session,
    *,
    company_id: UUID,
    actor_type: str,
    action: str,
    resource_type: str,
    actor_id: UUID | str | None = None,
    resource_id: UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    current_state: dict[str, Any] | None = None,
    write_jsonl: bool = True,
) -> None:
    """Best-effort persistent (+ optional JSONL) audit after a successful domain mutation."""
    merged = dict(metadata or {})
    if previous_state:
        merged["previous_state"] = previous_state
    if current_state:
        merged["current_state"] = current_state
    merged = sanitize_audit_metadata(merged)
    try:
        AuditService(store=audit_service.store, repository=AuditEventRepository(db)).persist(
            company_id=company_id,
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            actor_id=actor_id,
            resource_id=resource_id,
            metadata=merged,
        )
    except Exception:
        logger.exception(
            "audit_persist_failed action=%s resource_type=%s resource_id=%s",
            action,
            resource_type,
            resource_id,
        )
    if not write_jsonl:
        return
    try:
        audit_service.log(
            actor_id=str(actor_id) if actor_id is not None else "",
            actor_type=actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            metadata=merged,
            correlation_id=AuditService()._resolve_request_id(),
            previous_state=previous_state or {},
            current_state=current_state or {},
        )
    except Exception:
        logger.exception("audit_jsonl_failed action=%s", action)


def build_audit_service(db: Session) -> AuditService:
    return AuditService(
        store=audit_service.store,
        repository=AuditEventRepository(db),
        member_repository=CompanyMemberRepository(db),
    )


# Single global instance for convenience (JSONL store; bind a repository per request/session)
audit_service = AuditService()
