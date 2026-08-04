from __future__ import annotations

from enum import StrEnum


class InterviewType(StrEnum):
    PHONE = "phone"
    TECHNICAL = "technical"
    HR = "hr"
    MANAGERIAL = "managerial"
    FINAL = "final"


DEFAULT_INTERVIEW_TYPE = InterviewType.PHONE
