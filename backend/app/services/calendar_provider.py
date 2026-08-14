"""Provider-neutral calendar provider abstraction and built-in implementations."""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import uuid4

from app.core.calendar import CalendarProviderType
from app.schemas.calendar import (
    CalendarEventRequest,
    CalendarEventResult,
    CalendarProviderError,
)

logger = logging.getLogger("app.calendar_provider")


class CalendarProvider(Protocol):
    """Replaceable outbound calendar transport. No OAuth UI here."""

    provider_type: CalendarProviderType

    def create_event(self, request: CalendarEventRequest) -> CalendarEventResult: ...

    def update_event(self, request: CalendarEventRequest) -> CalendarEventResult: ...

    def cancel_event(self, request: CalendarEventRequest) -> CalendarEventResult: ...


class NullCalendarProvider:
    """No-op provider used when a company has no connected calendar."""

    provider_type = CalendarProviderType.NULL

    def create_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        return CalendarEventResult(
            external_event_id=f"null-{request.interview_id}",
            provider_type=self.provider_type,
            raw_status="skipped",
        )

    def update_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        return CalendarEventResult(
            external_event_id=request.external_event_id or f"null-{request.interview_id}",
            provider_type=self.provider_type,
            raw_status="skipped",
        )

    def cancel_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        return CalendarEventResult(
            external_event_id=request.external_event_id or f"null-{request.interview_id}",
            provider_type=self.provider_type,
            raw_status="cancelled",
        )


class FakeCalendarProvider:
    """In-memory provider for tests and local development. No network I/O."""

    provider_type = CalendarProviderType.FAKE

    def __init__(self) -> None:
        self.events: dict[str, CalendarEventRequest] = {}
        self.created: list[CalendarEventRequest] = []
        self.updated: list[CalendarEventRequest] = []
        self.cancelled: list[CalendarEventRequest] = []
        self.fail_next: CalendarProviderError | None = None

    def create_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        self._maybe_fail()
        event_id = request.external_event_id or f"fake-evt-{uuid4()}"
        stored = request.model_copy(update={"external_event_id": event_id})
        self.events[event_id] = stored
        self.created.append(stored)
        return CalendarEventResult(
            external_event_id=event_id,
            provider_type=self.provider_type,
            raw_status="created",
        )

    def update_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        self._maybe_fail()
        if not request.external_event_id:
            raise CalendarProviderError(
                "external_event_id required for update",
                retryable=False,
                error_code="missing_external_event_id",
            )
        self.events[request.external_event_id] = request
        self.updated.append(request)
        return CalendarEventResult(
            external_event_id=request.external_event_id,
            provider_type=self.provider_type,
            raw_status="updated",
        )

    def cancel_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        self._maybe_fail()
        event_id = request.external_event_id or f"fake-evt-{request.interview_id}"
        self.events.pop(event_id, None)
        self.cancelled.append(request)
        return CalendarEventResult(
            external_event_id=event_id,
            provider_type=self.provider_type,
            raw_status="cancelled",
        )

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise error


class UnimplementedCalendarProvider:
    """Placeholder for Google/Microsoft until OAuth + Graph clients land."""

    def __init__(self, provider_type: CalendarProviderType) -> None:
        self.provider_type = provider_type

    def create_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        raise CalendarProviderError(
            f"Calendar provider '{self.provider_type.value}' is not implemented yet",
            retryable=False,
            error_code="provider_not_implemented",
        )

    def update_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        raise CalendarProviderError(
            f"Calendar provider '{self.provider_type.value}' is not implemented yet",
            retryable=False,
            error_code="provider_not_implemented",
        )

    def cancel_event(self, request: CalendarEventRequest) -> CalendarEventResult:
        raise CalendarProviderError(
            f"Calendar provider '{self.provider_type.value}' is not implemented yet",
            retryable=False,
            error_code="provider_not_implemented",
        )


def build_calendar_provider(
    provider_type: str | CalendarProviderType,
    *,
    fake_provider: FakeCalendarProvider | None = None,
) -> CalendarProvider:
    ptype = (
        provider_type
        if isinstance(provider_type, CalendarProviderType)
        else CalendarProviderType(str(provider_type))
    )
    if ptype == CalendarProviderType.NULL:
        return NullCalendarProvider()
    if ptype == CalendarProviderType.FAKE:
        return fake_provider or FakeCalendarProvider()
    if ptype in {CalendarProviderType.GOOGLE, CalendarProviderType.MICROSOFT}:
        return UnimplementedCalendarProvider(ptype)
    raise CalendarProviderError(
        f"Unknown calendar provider: {ptype}",
        retryable=False,
        error_code="unknown_provider",
    )
