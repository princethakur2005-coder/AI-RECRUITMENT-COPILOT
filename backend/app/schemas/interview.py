from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType


class InterviewCreate(BaseModel):
    application_id: UUID
    interviewer_member_id: UUID
    interview_type: InterviewType
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str = Field(..., min_length=1, max_length=100)
    meeting_link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_schedule_window(self) -> "InterviewCreate":
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start")
        return self


class InterviewUpdate(BaseModel):
    interviewer_member_id: UUID | None = None
    interview_type: InterviewType | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    meeting_link: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    status: InterviewStatus | None = None


class InterviewInterviewerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    full_name: str
    email: EmailStr
    role: str


class InterviewApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    candidate_name: str | None = None
    candidate_email: str | None = None
    job_title: str | None = None


class InterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    company_id: UUID
    interviewer_member_id: UUID
    interview_type: InterviewType
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str
    meeting_link: str | None
    location: str | None
    notes: str | None
    status: InterviewStatus
    created_at: datetime
    updated_at: datetime
    interviewer: InterviewInterviewerSummary | None = None
    application: InterviewApplicationSummary | None = None
