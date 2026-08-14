from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.durable_job import DurableJobStatus, DurableJobType


class DurableJobSubmit(BaseModel):
    job_type: DurableJobType | str
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=128)
    company_id: UUID | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=50)
    priority: int = Field(default=0, ge=-100, le=100)
    scheduled_at: datetime | None = None

    @field_validator("payload")
    @classmethod
    def reject_sensitive_payload_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        blocked = {
            "password",
            "hashed_password",
            "token",
            "access_token",
            "refresh_token",
            "jwt",
            "secret",
            "api_key",
            "smtp_password",
            "authorization",
        }
        cleaned: dict[str, Any] = {}
        for key, item in (value or {}).items():
            key_l = str(key).lower()
            if key_l in blocked or any(part in key_l for part in ("password", "token", "secret", "jwt")):
                continue
            cleaned[key] = item
        return cleaned


class DurableJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: str
    status: DurableJobStatus
    payload: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int = 0
    max_attempts: int = 5
    priority: int = 0
    scheduled_at: datetime | None = None
    next_run_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    company_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_job(cls, row: Any) -> "DurableJobResponse":
        return cls(
            id=row.id,
            job_type=row.job_type,
            status=DurableJobStatus(row.status),
            payload=dict(row.payload_json or {}),
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            priority=row.priority,
            scheduled_at=row.scheduled_at,
            next_run_at=row.next_run_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            locked_at=row.locked_at,
            locked_by=row.locked_by,
            error_code=row.error_code,
            error_message=row.error_message,
            idempotency_key=row.idempotency_key,
            correlation_id=row.correlation_id,
            company_id=row.company_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
