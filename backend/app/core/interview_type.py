from __future__ import annotations

from enum import StrEnum


class InterviewType(StrEnum):
    PHONE = "phone"
    TECHNICAL = "technical"
    HR = "hr"
    MANAGERIAL = "managerial"
    FINAL = "final"
    AI_SCREENING = "ai_screening"


DEFAULT_INTERVIEW_TYPE = InterviewType.PHONE
