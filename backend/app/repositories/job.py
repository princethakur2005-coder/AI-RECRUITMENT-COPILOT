from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.job import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    """Repository for job-specific persistence and lookup operations."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, Job)

    def get_by_id_for_company(self, job_id: UUID, company_id: UUID) -> Job | None:
        statement = select(Job).where(Job.id == job_id, Job.company_id == company_id)
        return self.db.scalar(statement)

    def get_job_for_public_apply(self, job_id: UUID) -> Job | None:
        statement = select(Job).where(
            Job.id == job_id,
            Job.is_active.is_(True),
            Job.status == "open",
        )
        return self.db.scalar(statement)

    def list_by_company_id(self, company_id: UUID) -> list[Job]:
        statement = (
            select(Job)
            .where(Job.company_id == company_id)
            .order_by(Job.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_active_jobs(self, company_id: UUID) -> list[Job]:
        statement = select(Job).where(Job.company_id == company_id, Job.is_active.is_(True))
        return list(self.db.scalars(statement).all())

    def get_by_department(self, company_id: UUID, department: str) -> list[Job]:
        statement = select(Job).where(Job.company_id == company_id, Job.department == department)
        return list(self.db.scalars(statement).all())

    def search_jobs(self, company_id: UUID, query: str) -> list[Job]:
        search_term = f"%{query}%"
        statement = select(Job).where(
            Job.company_id == company_id,
            or_(
                Job.title.ilike(search_term),
                Job.description.ilike(search_term),
                Job.department.ilike(search_term),
                Job.location.ilike(search_term),
            ),
        )
        return list(self.db.scalars(statement).all())

    def set_job_intelligence(self, job: Job, intelligence: dict[str, object]) -> Job:
        return self.update(job, {"job_intelligence": intelligence})

    def get_job_counts(
        self,
        company_id: UUID,
        *,
        branch_id: UUID | None = None,
        job_id: UUID | None = None,
    ) -> dict[str, int]:
        filters = [Job.company_id == company_id]
        if branch_id is not None:
            filters.append(Job.branch_id == branch_id)
        if job_id is not None:
            filters.append(Job.id == job_id)

        row = self.db.execute(
            select(
                func.count(Job.id),
                func.coalesce(func.sum(case((Job.is_active.is_(True), 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (and_(Job.is_active.is_(True), Job.status == "open"), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(*filters),
        ).one()
        return {"total": int(row[0] or 0), "active": int(row[1] or 0), "open": int(row[2] or 0)}

    def count_by_department(self, company_id: UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Job.department, func.count(Job.id))
            .where(Job.company_id == company_id)
            .group_by(Job.department),
        ).all()
        result: dict[str, int] = {}
        for department, count in rows:
            label = department or "Unspecified"
            result[label] = int(count)
        return result

    def list_with_application_counts(self, company_id: UUID) -> list[dict[str, object]]:
        application_count = func.count(Application.id).label("application_count")
        statement = (
            select(
                Job.id,
                Job.title,
                Job.location,
                Job.department,
                Job.status,
                Job.created_at,
                application_count,
            )
            .outerjoin(Application, Application.job_id == Job.id)
            .where(Job.company_id == company_id)
            .group_by(Job.id)
            .order_by(Job.created_at.desc())
        )
        rows = self.db.execute(statement).all()
        return [dict(row._mapping) for row in rows]
