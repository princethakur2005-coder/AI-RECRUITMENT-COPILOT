from __future__ import annotations

from enum import StrEnum


class InterviewStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


DEFAULT_INTERVIEW_STATUS = InterviewStatus.SCHEDULED
