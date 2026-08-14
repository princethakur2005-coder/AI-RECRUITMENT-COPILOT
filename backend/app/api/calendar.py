"""Tenant-scoped calendar integration management API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.schemas.calendar import (
    CalendarIntegrationCreate,
    CalendarIntegrationResponse,
    InterviewCalendarSyncResponse,
)
from app.services.calendar_integration_service import CalendarIntegrationService

router = APIRouter(tags=["calendar"])


def get_calendar_integration_service(db: Session = Depends(get_db)) -> CalendarIntegrationService:
    return CalendarIntegrationService(
        CalendarIntegrationRepository(db),
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


@router.post(
    "/companies/{company_id}/calendar-integrations",
    response_model=CalendarIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_integration(
    company_id: UUID,
    payload: CalendarIntegrationCreate,
    current_user: User = Depends(get_current_user),
    service: CalendarIntegrationService = Depends(get_calendar_integration_service),
) -> CalendarIntegrationResponse:
    try:
        return service.create(current_user, company_id, payload)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.get(
    "/companies/{company_id}/calendar-integrations",
    response_model=list[CalendarIntegrationResponse],
)
def list_calendar_integrations(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CalendarIntegrationService = Depends(get_calendar_integration_service),
) -> list[CalendarIntegrationResponse]:
    try:
        return service.list(current_user, company_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.get(
    "/companies/{company_id}/calendar-integrations/{integration_id}",
    response_model=CalendarIntegrationResponse,
)
def get_calendar_integration(
    company_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CalendarIntegrationService = Depends(get_calendar_integration_service),
) -> CalendarIntegrationResponse:
    try:
        return service.get(current_user, company_id, integration_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.post(
    "/companies/{company_id}/calendar-integrations/{integration_id}/disable",
    response_model=CalendarIntegrationResponse,
)
def disable_calendar_integration(
    company_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CalendarIntegrationService = Depends(get_calendar_integration_service),
) -> CalendarIntegrationResponse:
    try:
        return service.disable(current_user, company_id, integration_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.delete(
    "/companies/{company_id}/calendar-integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_calendar_integration(
    company_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CalendarIntegrationService = Depends(get_calendar_integration_service),
) -> None:
    try:
        service.delete(current_user, company_id, integration_id)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _map_errors(exc) from exc


@router.get(
    "/interviews/{interview_id}/calendar-sync",
    response_model=InterviewCalendarSyncResponse,
)
def get_interview_calendar_sync(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterviewCalendarSyncResponse:
    membership = CompanyMemberRepository(db).get_by_user_id(current_user.id)
    if membership is None or not membership.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Active company membership required")
    sync = InterviewCalendarSyncRepository(db).get_by_interview_id(interview_id)
    if sync is None or sync.company_id != membership.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar sync state not found")
    return InterviewCalendarSyncResponse.from_orm_row(sync)
