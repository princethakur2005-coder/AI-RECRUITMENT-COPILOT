"""Staff notification API — authenticated company users only."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.notification import NotificationStatus
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.notification import NotificationRepository
from app.repositories.notification_preference import NotificationPreferenceRepository
from app.schemas.notification import (
    NotificationFilter,
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationMarkReadRequest,
    NotificationResponse,
    NotificationSummaryResponse,
)
from app.schemas.notification_preference import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.services.notification import NotificationService
from app.services.notification_preference import NotificationPreferenceService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    member_repository = CompanyMemberRepository(db)
    preference_service = NotificationPreferenceService(
        NotificationPreferenceRepository(db),
        member_repository,
    )
    return NotificationService(
        NotificationRepository(db),
        member_repository,
        preference_service=preference_service,
    )


def get_preference_service(db: Session = Depends(get_db)) -> NotificationPreferenceService:
    return NotificationPreferenceService(
        NotificationPreferenceRepository(db),
        CompanyMemberRepository(db),
    )


def _handle_errors(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/preferences", response_model=NotificationPreferenceResponse)
def get_my_notification_preferences(
    current_user: User = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> NotificationPreferenceResponse:
    try:
        return service.get_for_user(current_user)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
def update_my_notification_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    service: NotificationPreferenceService = Depends(get_preference_service),
) -> NotificationPreferenceResponse:
    try:
        return service.update_for_user(current_user, payload)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.get("", response_model=NotificationListResponse)
def list_my_notifications(
    status_filter: NotificationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    filters = NotificationFilter(status=status_filter, limit=limit, offset=offset)
    return service.list_for_user(current_user, filters)


@router.get("/summary", response_model=NotificationSummaryResponse)
def get_my_notification_summary(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSummaryResponse:
    return service.summary_for_user(current_user)


@router.post("/read-all", response_model=NotificationMarkAllReadResponse)
def mark_all_my_notifications_read(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationMarkAllReadResponse:
    return service.mark_all_read_for_user(current_user)


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_my_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    try:
        return service.get_for_user(current_user, notification_id)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_my_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    try:
        return service.mark_for_user(current_user, notification_id, NotificationStatus.READ)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise


@router.patch("/{notification_id}", response_model=NotificationResponse)
def patch_my_notification(
    notification_id: UUID,
    payload: NotificationMarkReadRequest,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Mark read/unread — compatible with the existing notifications UI contract."""
    try:
        return service.mark_for_user(current_user, notification_id, payload.target_status)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc)
        raise
