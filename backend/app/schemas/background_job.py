from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BackgroundJobStatus(str, Enum):
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJobPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class BackgroundJobRetryMetadata(BaseModel):
    max_retries: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    retry_backoff_seconds: int = Field(default=0, ge=0)
    next_retry_at: datetime | None = None


class BackgroundJobExecutionEvent(BaseModel):
    event: str
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class BackgroundJobCreate(BaseModel):
    job_type: str = Field(..., min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None
    priority: BackgroundJobPriority = BackgroundJobPriority.NORMAL
    retry: BackgroundJobRetryMetadata = Field(default_factory=BackgroundJobRetryMetadata)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackgroundJobFilter(BaseModel):
    job_type: str | None = None
    status: BackgroundJobStatus | None = None
    priority: BackgroundJobPriority | None = None
    scheduled_after: datetime | None = None
    scheduled_before: datetime | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BackgroundJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: BackgroundJobStatus
    priority: BackgroundJobPriority
    retry: BackgroundJobRetryMetadata = Field(default_factory=BackgroundJobRetryMetadata)
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_history: list[BackgroundJobExecutionEvent] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BackgroundJobListResponse(BaseModel):
    items: list[BackgroundJobResponse] = Field(default_factory=list)
    total: int = 0
