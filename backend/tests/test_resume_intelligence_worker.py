"""Focused tests for Durable AI Resume Parsing, Skill Extraction & Candidate Ranking Execution."""

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.durable_job import DurableJobStatus, DurableJobType, JobExecutionError
from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.main import app
from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.durable_job import DurableJob
from app.models.job import Job
from app.models.user import User
from app.repositories.durable_job import DurableJobRepository
from app.schemas.durable_job import DurableJobSubmit
from app.services.durable_job_service import DurableJobService
from app.services.durable_job_worker import DurableJobWorker, build_job_service
from app.services.job_handlers.resume_intelligence import (
    ResumeIntelligenceJobHandler,
    normalize_recommendation,
    process_resume_intelligence,
)
from app.utils.resume_parser import ResumeParser


@pytest.fixture
def test_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class WorkerTestWorld:
    def __init__(self, db: Session, tmp_path: Path) -> None:
        self.db = db
        self.tmp_path = tmp_path

        self.user = User(
            id=uuid4(),
            email="recruiter@apexsolutions.io",
            full_name="Alex Recruiter",
            hashed_password=hash_password("RecruiterPass123!"),
            is_active=True,
        )
        self.db.add(self.user)
        self.db.flush()

        self.company = Company(
            id=uuid4(),
            name="Apex Solutions",
            slug=f"apex-{uuid4().hex[:6]}",
            owner_id=self.user.id,
            is_active=True,
        )
        self.db.add(self.company)

        self.other_company = Company(
            id=uuid4(),
            name="Other Corp",
            slug=f"other-{uuid4().hex[:6]}",
            owner_id=self.user.id,
            is_active=True,
        )
        self.db.add(self.other_company)
        self.db.flush()

        self.member = CompanyMember(
            id=uuid4(),
            user_id=self.user.id,
            company_id=self.company.id,
            role="recruiter",
            is_active=True,
        )
        self.db.add(self.member)

        self.job = Job(
            id=uuid4(),
            company_id=self.company.id,
            company_member_id=self.member.id,
            title="Senior Python Backend Engineer",
            description="We need a strong Python engineer with experience in FastAPI, PostgreSQL, Docker, and Kubernetes.",
            department="Engineering",
            location="San Francisco, CA",
            employment_type="full_time",
            experience_level="senior",
            status="open",
            is_active=True,
            job_intelligence={
                "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
                "preferred_skills": ["AWS", "Redis"],
            },
        )
        self.db.add(self.job)

        self.candidate = Candidate(
            id=uuid4(),
            email="candidate.dev@example.com",
            first_name="Jordan",
            last_name="Lee",
            full_name="Jordan Lee",
            status="new",
            is_active=True,
        )
        self.db.add(self.candidate)

        self.resume_file = tmp_path / "jordan_lee_resume.txt"
        self.resume_file.write_text(
            "JORDAN LEE\nSenior Software Engineer\n\n"
            "Summary:\nExperienced backend engineer with 6+ years designing scalable distributed systems.\n\n"
            "Technical Skills:\nPython, FastAPI, PostgreSQL, Docker, Redis, Git, Linux, Kubernetes\n\n"
            "Experience:\n"
            "Senior Backend Engineer at TechCorp (2021-Present)\n"
            "Built high-throughput microservices using FastAPI and PostgreSQL with Docker containerization.\n\n"
            "Software Developer at WebInc (2018-2021)\n"
            "Engineered Python REST APIs and relational database models.\n",
            encoding="utf-8",
        )

        self.application = Application(
            id=uuid4(),
            company_id=self.company.id,
            job_id=self.job.id,
            candidate_id=self.candidate.id,
            resume_path=str(self.resume_file),
            status="applied",
            source="public_apply",
        )
        self.db.add(self.application)
        self.db.commit()


def test_recommendation_normalization():
    assert normalize_recommendation("Strongly recommend this candidate", 90.0) == "strongly_recommend"
    assert normalize_recommendation("Recommend for interview", 70.0) == "recommend"
    assert normalize_recommendation("Review skills carefully", 55.0) == "neutral"
    assert normalize_recommendation("Reject - missing basic qualifications", 30.0) == "reject"
    assert normalize_recommendation(None, 85.0) == "strongly_recommend"
    assert normalize_recommendation(None, 70.0) == "recommend"
    assert normalize_recommendation(None, 52.0) == "neutral"
    assert normalize_recommendation(None, 40.0) == "reject"


def test_worker_handler_processes_resume_and_updates_db(test_db: Session, tmp_path: Path):
    world = WorkerTestWorld(test_db, tmp_path)
    job_service = build_job_service(test_db)

    submitted = job_service.submit(
        DurableJobSubmit(
            job_type=DurableJobType.RESUME_INTELLIGENCE,
            payload={
                "application_id": str(world.application.id),
                "resume_path": str(world.resume_file),
            },
            company_id=world.company.id,
        )
    )
    assert submitted.status == DurableJobStatus.PENDING

    worker = DurableJobWorker(job_service, worker_id="test-worker-1")
    processed = worker.process_one(job_types=[DurableJobType.RESUME_INTELLIGENCE.value])
    assert processed is True

    stored_job = job_service.get(submitted.id)
    assert stored_job is not None
    assert stored_job.status == DurableJobStatus.SUCCEEDED

    app_row = test_db.scalar(select(Application).where(Application.id == world.application.id))
    assert app_row is not None
    assert app_row.ai_status == "completed"
    assert app_row.fit_score is not None
    assert app_row.fit_score >= 50.0
    assert app_row.evaluation_summary is not None
    assert app_row.status in ("shortlisted", "screening")

    cand_row = test_db.scalar(select(Candidate).where(Candidate.id == world.candidate.id))
    assert cand_row is not None
    assert cand_row.job_id == world.job.id
    assert cand_row.resume_path == str(world.resume_file)
    assert cand_row.skills is not None
    assert "Python" in cand_row.skills or "FastAPI" in cand_row.skills
    assert cand_row.status in ("shortlisted", "screening")

    analysis = test_db.scalar(
        select(ApplicationAIAnalysis).where(ApplicationAIAnalysis.application_id == world.application.id)
    )
    assert analysis is not None
    assert analysis.overall_score == int(app_row.fit_score)
    assert analysis.recommendation in ("strongly_recommend", "recommend", "neutral", "reject")
    assert len(analysis.matched_skills) > 0

    job_row = test_db.scalar(select(Job).where(Job.id == world.job.id))
    assert job_row.job_intelligence is not None
    assert "candidate_match_summary" in job_row.job_intelligence
    assert "Jordan Lee" in job_row.job_intelligence["candidate_match_summary"]


def test_candidate_api_returns_ai_fields_and_resume_stream(test_db: Session, tmp_path: Path):
    world = WorkerTestWorld(test_db, tmp_path)
    handler = ResumeIntelligenceJobHandler(test_db)

    durable_job = DurableJob(
        job_type=DurableJobType.RESUME_INTELLIGENCE.value,
        payload_json={"application_id": str(world.application.id)},
        company_id=world.company.id,
    )
    handler.execute(durable_job)

    app.dependency_overrides[get_db] = lambda: test_db
    client = TestClient(app)

    try:
        res = client.get(f"/candidates/{world.candidate.id}")
        assert res.status_code == 200
        data = res.json()

        assert data["id"] == str(world.candidate.id)
        assert data["job_id"] == str(world.job.id)
        assert data["fit_score"] is not None
        assert data["fit_score"] > 0
        assert data["evaluation_summary"] is not None
        assert len(data["matched_skills"]) > 0
        assert data["candidate_match_summary"] is not None
        assert data["resume_preview_url"] == f"/candidates/{world.candidate.id}/resume"

        resume_res = client.get(f"/candidates/{world.candidate.id}/resume")
        assert resume_res.status_code == 200
        assert "inline" in resume_res.headers.get("content-disposition", "")
        assert b"JORDAN LEE" in resume_res.content

        list_res = client.get("/candidates")
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) >= 1
        cand_item = next(c for c in items if c["id"] == str(world.candidate.id))
        assert cand_item["fit_score"] is not None
        assert cand_item["evaluation_summary"] is not None

    finally:
        app.dependency_overrides.clear()


def test_tenant_isolation_violation_rejected(test_db: Session, tmp_path: Path):
    world = WorkerTestWorld(test_db, tmp_path)
    handler = ResumeIntelligenceJobHandler(test_db)

    world.application.company_id = world.other_company.id
    test_db.add(world.application)
    test_db.commit()

    durable_job = DurableJob(
        job_type=DurableJobType.RESUME_INTELLIGENCE.value,
        payload_json={"application_id": str(world.application.id)},
        company_id=world.other_company.id,
    )

    with pytest.raises(JobExecutionError) as exc_info:
        handler.execute(durable_job)

    assert exc_info.value.error_code == "tenant_mismatch"
    assert exc_info.value.retryable is False

    test_db.refresh(world.application)
    assert world.application.ai_status == "failed"


def test_fail_safe_missing_resume_file(test_db: Session, tmp_path: Path):
    world = WorkerTestWorld(test_db, tmp_path)
    handler = ResumeIntelligenceJobHandler(test_db)

    world.application.resume_path = str(tmp_path / "nonexistent_resume.pdf")
    test_db.add(world.application)
    test_db.commit()

    durable_job = DurableJob(
        job_type=DurableJobType.RESUME_INTELLIGENCE.value,
        payload_json={"application_id": str(world.application.id)},
        company_id=world.company.id,
    )

    with pytest.raises(JobExecutionError) as exc_info:
        handler.execute(durable_job)

    assert exc_info.value.error_code == "resume_file_not_found"
    assert exc_info.value.retryable is True

    test_db.refresh(world.application)
    assert world.application.ai_status == "failed"
