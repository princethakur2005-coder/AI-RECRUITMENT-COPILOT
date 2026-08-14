"""Calendar integration and sync schemas — provider-neutral, no secrets."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.calendar import (
    CalendarIntegrationStatus,
    CalendarProviderType,
    CalendarSyncOperation,
    CalendarSyncStatus,
)


class CalendarAttendee(BaseModel):
    email: str
    display_name: str | None = None
    role: str | None = None  # interviewer | candidate | optional


class CalendarEventRequest(BaseModel):
    """Provider-neutral create/update payload derived from Interview."""

    interview_id: UUID
    company_id: UUID
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    timezone: str
    location: str | None = None
    meeting_link: str | None = None
    attendees: list[CalendarAttendee] = Field(default_factory=list)
    external_event_id: str | None = None
    external_calendar_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def strip_sensitive_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, item in (value or {}).items():
            key_l = str(key).lower()
            if any(part in key_l for part in ("password", "token", "secret", "jwt", "credential")):
                continue
            cleaned[str(key)] = item
        return cleaned


class CalendarEventResult(BaseModel):
    external_event_id: str
    provider_type: CalendarProviderType | str
    raw_status: str | None = None


class CalendarProviderError(Exception):
    """Raised by calendar providers to signal retryable vs permanent failure."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.error_code = error_code


class CalendarIntegrationCreate(BaseModel):
    provider_type: CalendarProviderType = CalendarProviderType.FAKE
    display_name: str | None = Field(default=None, max_length=255)
    external_calendar_id: str | None = Field(default=None, max_length=255)
    # Accepted once at create/update; sealed immediately; never returned.
    credentials: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalendarIntegrationResponse(BaseModel):
    """Public view — never includes credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    provider_type: CalendarProviderType
    status: CalendarIntegrationStatus
    display_name: str | None = None
    external_calendar_id: str | None = None
    has_credentials: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: Any) -> "CalendarIntegrationResponse":
        return cls(
            id=row.id,
            company_id=row.company_id,
            provider_type=CalendarProviderType(row.provider_type),
            status=CalendarIntegrationStatus(row.status),
            display_name=row.display_name,
            external_calendar_id=row.external_calendar_id,
            has_credentials=bool(row.credentials_sealed),
            metadata=dict(row.metadata_json or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class InterviewCalendarSyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interview_id: UUID
    company_id: UUID
    calendar_integration_id: UUID | None = None
    sync_status: CalendarSyncStatus
    external_event_id: str | None = None
    last_operation: CalendarSyncOperation | str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: Any) -> "InterviewCalendarSyncResponse":
        return cls(
            id=row.id,
            interview_id=row.interview_id,
            company_id=row.company_id,
            calendar_integration_id=row.calendar_integration_id,
            sync_status=CalendarSyncStatus(row.sync_status),
            external_event_id=row.external_event_id,
            last_operation=row.last_operation,
            last_error_code=row.last_error_code,
            last_error_message=row.last_error_message,
            last_synced_at=row.last_synced_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
