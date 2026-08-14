"""Provider-neutral calendar integration contracts."""

from __future__ import annotations

from enum import StrEnum


class CalendarProviderType(StrEnum):
    """Registered provider identifiers. Implementations are swap-in."""

    NULL = "null"
    FAKE = "fake"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class CalendarIntegrationStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class CalendarSyncStatus(StrEnum):
    """Interview ↔ external calendar sync state (not interview workflow state)."""

    NOT_CONNECTED = "not_connected"
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CalendarSyncOperation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"


# Scheduling fields that trigger calendar update when changed.
CALENDAR_SYNC_SCHEDULE_FIELDS: frozenset[str] = frozenset(
    {
        "scheduled_start",
        "scheduled_end",
        "timezone",
        "meeting_link",
        "location",
        "interviewer_member_id",
        "interview_type",
    }
)
