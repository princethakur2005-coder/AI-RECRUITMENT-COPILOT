"""Read-only tenant-scoped audit log API. No public create/update/delete."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.core.audit import sanitize_audit_metadata
from app.models.audit_event import AuditEvent
from app.models.user import User
from app.schemas.audit_log import AuditLogEvent, AuditLogListResponse
from app.services.audit_service import AuditService, build_audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return build_audit_service(db)


def _handle_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


def _to_event(row: AuditEvent) -> AuditLogEvent:
    metadata = sanitize_audit_metadata(dict(row.metadata_json or {}))
    previous_state = metadata.get("previous_state") if isinstance(metadata.get("previous_state"), dict) else {}
    current_state = metadata.get("current_state") if isinstance(metadata.get("current_state"), dict) else {}
    if previous_state:
        previous_state = sanitize_audit_metadata(previous_state)
    if current_state:
        current_state = sanitize_audit_metadata(current_state)
    return AuditLogEvent(
        id=row.id,
        timestamp=row.created_at,
        created_at=row.created_at,
        company_id=row.company_id,
        actor_id=str(row.actor_id) if row.actor_id is not None else None,
        actor_type=row.actor_type,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=str(row.resource_id) if row.resource_id is not None else None,
        entity_type=row.resource_type,
        entity_id=str(row.resource_id) if row.resource_id is not None else None,
        previous_state=previous_state,
        current_state=current_state,
        metadata=metadata,
        request_id=row.request_id,
        correlation_id=row.request_id,
    )


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    action: str | None = Query(None, max_length=100),
    resource_type: str | None = Query(None, max_length=100),
    resource_id: UUID | None = Query(None),
    actor_id: UUID | None = Query(None),
    actor_type: str | None = Query(None, max_length=100),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
    offset: int = Query(0, ge=0, le=10_000),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: AuditService = Depends(get_audit_service),
) -> AuditLogListResponse:
    try:
        items, total = service.list_for_user(
            current_user,
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
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise
    return AuditLogListResponse(
        items=[_to_event(row) for row in items],
        total=total,
        offset=offset,
        limit=limit,
    )
