from __future__ import annotations

from typing import Any

from app.models.job import Job
from app.repositories.job import JobRepository
from app.services.base import BaseService
from app.services.job_intelligence_engine import JobIntelligenceEngine


class JobService(BaseService[Job]):
    """Service layer for job-related business operations."""

    def __init__(self, repository: JobRepository, intelligence_engine: JobIntelligenceEngine | None = None) -> None:
        super().__init__(repository)
        self.intelligence_engine = intelligence_engine or JobIntelligenceEngine()

    def create_job(self, job: Job) -> Job:
        created = self.repository.create(job)
        return self.refresh_job_intelligence(created)

    def update(self, db_obj: Job, obj_in: dict[str, Any]) -> Job:
        updated = self.repository.update(db_obj, obj_in)
        if "description" in obj_in or "title" in obj_in or not updated.job_intelligence:
            return self.refresh_job_intelligence(updated)
        return updated

    def get_active_jobs(self) -> list[Job]:
        return self.repository.get_active_jobs()

    def get_jobs_by_department(self, department: str) -> list[Job]:
        return self.repository.get_by_department(department)

    def search_jobs(self, query: str) -> list[Job]:
        return self.repository.search_jobs(query)

    def refresh_job_intelligence(self, job: Job) -> Job:
        intelligence = self.intelligence_engine.build_intelligence(
            job_description=job.description or "",
            title=job.title,
        )
        return self.repository.set_job_intelligence(job, intelligence)
