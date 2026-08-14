"""Tenant-scoped webhook management API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.webhook import WebhookRepository
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookResponse,
    WebhookUpdate,
)
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/companies/{company_id}/webhooks", tags=["webhooks"])


def get_webhook_service(db: Session = Depends(get_db)) -> WebhookService:
    return WebhookService(
        WebhookRepository(db),
        CompanyRepository(db),
        CompanyMemberRepository(db),
    )


def _map_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


@router.post("", response_model=WebhookCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    company_id: UUID,
    payload: WebhookCreate,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookCreatedResponse:
    try:
        return service.create(current_user, company_id, payload)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookResponse]:
    try:
        return service.list(current_user, company_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(
    company_id: UUID,
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    try:
        return service.get(current_user, company_id, webhook_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.patch("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    company_id: UUID,
    webhook_id: UUID,
    payload: WebhookUpdate,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    try:
        return service.update(current_user, company_id, webhook_id, payload)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.post("/{webhook_id}/enable", response_model=WebhookResponse)
def enable_webhook(
    company_id: UUID,
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    try:
        return service.set_active(current_user, company_id, webhook_id, is_active=True)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.post("/{webhook_id}/disable", response_model=WebhookResponse)
def disable_webhook(
    company_id: UUID,
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    try:
        return service.set_active(current_user, company_id, webhook_id, is_active=False)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    company_id: UUID,
    webhook_id: UUID,
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> None:
    try:
        service.delete(current_user, company_id, webhook_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc
