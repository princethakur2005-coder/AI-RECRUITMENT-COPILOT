from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class YearsOfExperience(BaseModel):
    text: str | None = None
    minimum: int | None = None
    maximum: int | None = None


class JobIntelligence(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    years_of_experience: YearsOfExperience = Field(default_factory=YearsOfExperience)
    seniority_level: str | None = None
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, str] | None = None


class JobBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    department: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=100)
    experience_level: str | None = Field(default=None, max_length=100)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=10)
    openings: int = Field(default=1, ge=1)
    status: str = Field(default="draft", max_length=50)
    is_active: bool = True


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    department: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=100)
    experience_level: str | None = Field(default=None, max_length=100)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=10)
    openings: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class JobResponse(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_intelligence: JobIntelligence | None = None
    created_at: datetime
    updated_at: datetime
