from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    """Repository for job-specific persistence and lookup operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Job)

    def get_active_jobs(self) -> list[Job]:
        statement = select(Job).where(Job.is_active.is_(True))
        return list(self.db.scalars(statement).all())

    def get_by_department(self, department: str) -> list[Job]:
        statement = select(Job).where(Job.department == department)
        return list(self.db.scalars(statement).all())

    def search_jobs(self, query: str) -> list[Job]:
        search_term = f"%{query}%"
        statement = select(Job).where(
            or_(
                Job.title.ilike(search_term),
                Job.description.ilike(search_term),
                Job.department.ilike(search_term),
                Job.location.ilike(search_term),
            )
        )
        return list(self.db.scalars(statement).all())

    def set_job_intelligence(self, job: Job, intelligence: dict[str, object]) -> Job:
        return self.update(job, {"job_intelligence": intelligence})
