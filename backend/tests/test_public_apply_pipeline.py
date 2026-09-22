"""Public Job Application Link, Candidate Intake & AI Ingestion Trigger tests."""

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
from app.services.candidate_ranking import calculate_overall_rank_score
from app.services.durable_job_service import DurableJobService
from app.services.job_handlers.resume_intelligence import ResumeIntelligenceJobHandler
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


class PublicApplyTestWorld:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.owner = User(
            full_name="Acme Owner",
            email=f"owner-{uuid4().hex[:6]}@acme.test",
            hashed_password=hash_password("OwnerPass1!"),
            role="admin",
            is_active=True,
        )
        self.db.add(self.owner)
        self.db.flush()

        self.company = Company(
            name="Acme Corp",
            slug=f"acme-{uuid4().hex[:6]}",
            owner_id=self.owner.id,
            is_active=True,
        )
        self.db.add(self.company)
        self.db.flush()

        self.owner.company_id = self.company.id
        self.db.add(self.owner)

        self.member = CompanyMember(
            company_id=self.company.id,
            user_id=self.owner.id,
            role="company_admin",
            is_active=True,
        )
        self.db.add(self.member)
        self.db.flush()

        self.open_job = Job(
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.owner.id,
            title="Senior Backend Engineer",
            department="Engineering",
            location="Remote",
            employment_type="full_time",
            experience_level="Senior",
            description="We are seeking an experienced Backend Engineer to build scalable distributed systems.",
            job_intelligence={"required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"]},
            status="open",
            is_active=True,
        )
        self.db.add(self.open_job)

        self.second_open_job = Job(
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.owner.id,
            title="Frontend Engineer",
            department="Engineering",
            location="Remote",
            employment_type="full_time",
            experience_level="Mid",
            description="Seeking a Frontend Engineer skilled in React and TypeScript.",
            job_intelligence={"required_skills": ["React", "TypeScript", "Next.js"]},
            status="open",
            is_active=True,
        )
        self.db.add(self.second_open_job)

        self.draft_job = Job(
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.owner.id,
            title="Draft Engineering Lead",
            department="Engineering",
            status="draft",
            is_active=True,
        )
        self.db.add(self.draft_job)

        self.closed_job = Job(
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.owner.id,
            title="Closed Product Manager",
            department="Product",
            status="closed",
            is_active=True,
        )
        self.db.add(self.closed_job)

        self.db.commit()


@pytest.fixture
def client(test_db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: test_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_public_job_details_open_job_without_auth(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    # Test /public/jobs/{job_id}
    resp = client.get(f"/public/jobs/{world.open_job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(world.open_job.id)
    assert data["title"] == "Senior Backend Engineer"
    assert data["department"] == "Engineering"
    assert data["location"] == "Remote"
    assert data["company_name"] == "Acme Corp"
    assert "Python" in data["requirements"]
    assert "FastAPI" in data["requirements"]

    # Test /api/v1/public/jobs/{job_id}
    resp_v1 = client.get(f"/api/v1/public/jobs/{world.open_job.id}")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["id"] == str(world.open_job.id)


def test_public_job_details_draft_closed_or_missing_returns_404(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    # Draft job
    resp_draft = client.get(f"/public/jobs/{world.draft_job.id}")
    assert resp_draft.status_code == 404

    # Closed job
    resp_closed = client.get(f"/public/jobs/{world.closed_job.id}")
    assert resp_closed.status_code == 404

    # Non-existent job
    resp_missing = client.get(f"/public/jobs/{uuid4()}")
    assert resp_missing.status_code == 404


def test_public_apply_success_and_durable_job_enqueued(test_db: Session, client: TestClient, tmp_path: Path):
    world = PublicApplyTestWorld(test_db)

    dummy_pdf = b"%PDF-1.4 John Doe Python FastAPI PostgreSQL Docker Senior Engineer"
    files = {"resume": ("john_doe_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    data = {
        "full_name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "+1-555-0199",
    }

    resp = client.post(f"/public/jobs/{world.open_job.id}/apply", data=data, files=files)
    assert resp.status_code == 201
    result = resp.json()
    assert result["job_id"] == str(world.open_job.id)
    assert result["status"] == "applied"

    # Verify Candidate was created
    candidate = test_db.scalar(select(Candidate).where(Candidate.email == "john.doe@example.com"))
    assert candidate is not None
    assert candidate.full_name == "John Doe"
    assert candidate.first_name == "John"
    assert candidate.last_name == "Doe"
    assert candidate.phone == "+1-555-0199"
    assert candidate.job_id == world.open_job.id

    # Verify Application was created with correct tenant company_id
    from uuid import UUID
    application = test_db.scalar(select(Application).where(Application.id == UUID(result["application_id"])))
    assert application is not None
    assert application.company_id == world.company.id
    assert application.candidate_id == candidate.id
    assert application.job_id == world.open_job.id
    assert application.source == "careers_page"

    # Verify Durable background job was enqueued
    durable_jobs = list(
        test_db.scalars(
            select(DurableJob).where(
                DurableJob.job_type == DurableJobType.RESUME_INTELLIGENCE.value,
                DurableJob.company_id == world.company.id,
            )
        ).all()
    )
    assert len(durable_jobs) == 1
    job = durable_jobs[0]
    assert job.status == DurableJobStatus.PENDING.value
    assert job.payload["application_id"] == str(application.id)
    assert job.payload["candidate_id"] == str(candidate.id)
    assert job.payload["job_id"] == str(world.open_job.id)
    assert job.payload["company_id"] == str(world.company.id)


def test_public_apply_duplicate_conflict(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    dummy_pdf = b"%PDF-1.4 Jane Doe Python Developer"
    files = {"resume": ("jane_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    data = {
        "full_name": "Jane Doe",
        "email": "jane.doe@example.com",
    }

    resp1 = client.post(f"/public/jobs/{world.open_job.id}/apply", data=data, files=files)
    assert resp1.status_code == 201

    # Apply again to same job
    files2 = {"resume": ("jane_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    resp2 = client.post(f"/public/jobs/{world.open_job.id}/apply", data=data, files=files2)
    assert resp2.status_code == 409
    assert "already applied" in resp2.json()["detail"].lower()


def test_public_apply_same_candidate_multiple_jobs(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    dummy_pdf = b"%PDF-1.4 Bob Builder Full Stack Engineer"
    files1 = {"resume": ("bob_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    data = {
        "full_name": "Bob Builder",
        "email": "bob@example.com",
    }

    # Apply to job 1
    resp1 = client.post(f"/public/jobs/{world.open_job.id}/apply", data=data, files=files1)
    assert resp1.status_code == 201
    cand1_id = resp1.json()["candidate_id"]

    # Apply to job 2 with same email
    files2 = {"resume": ("bob_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    resp2 = client.post(f"/public/jobs/{world.second_open_job.id}/apply", data=data, files=files2)
    assert resp2.status_code == 201
    cand2_id = resp2.json()["candidate_id"]

    # Must reuse candidate identity
    assert cand1_id == cand2_id

    # Verify two distinct applications exist
    candidate = test_db.scalar(select(Candidate).where(Candidate.email == "bob@example.com"))
    apps = list(test_db.scalars(select(Application).where(Application.candidate_id == candidate.id)).all())
    assert len(apps) == 2


def test_public_apply_invalid_file_type_rejected(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    bad_file = b"malicious executable binary"
    files = {"resume": ("resume.exe", io.BytesIO(bad_file), "application/octet-stream")}
    data = {
        "full_name": "Bad Actor",
        "email": "bad@example.com",
    }

    resp = client.post(f"/public/jobs/{world.open_job.id}/apply", data=data, files=files)
    assert resp.status_code == 400
    assert "PDF and DOCX" in resp.json()["detail"]


def test_public_apply_non_open_job_rejected(test_db: Session, client: TestClient):
    world = PublicApplyTestWorld(test_db)

    dummy_pdf = b"%PDF-1.4 Valid PDF"
    files = {"resume": ("resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    data = {"full_name": "Test User", "email": "test@example.com"}

    resp = client.post(f"/public/jobs/{world.draft_job.id}/apply", data=data, files=files)
    assert resp.status_code == 404


def test_resume_intelligence_job_handler_execution(test_db: Session, tmp_path: Path):
    world = PublicApplyTestWorld(test_db)

    # Create dummy resume text file with extension .docx
    # Mock ResumeParser.extract_text to return structured text
    resume_file = tmp_path / "candidate_resume.pdf"
    resume_file.write_bytes(b"%PDF-1.4 Mocked resume")

    candidate = Candidate(
        first_name="Ada",
        last_name="Lovelace",
        full_name="Ada Lovelace",
        email="ada@example.com",
        job_id=world.open_job.id,
        status="new",
        is_active=True,
    )
    test_db.add(candidate)
    test_db.flush()

    application = Application(
        company_id=world.company.id,
        job_id=world.open_job.id,
        candidate_id=candidate.id,
        resume_path=str(resume_file),
        status="new",
        source="careers_page",
    )
    test_db.add(application)
    test_db.commit()

    durable_job = DurableJob(
        job_type=DurableJobType.RESUME_INTELLIGENCE.value,
        status=DurableJobStatus.RUNNING.value,
        payload_json={
            "application_id": str(application.id),
            "candidate_id": str(candidate.id),
            "job_id": str(world.open_job.id),
            "company_id": str(world.company.id),
            "resume_path": str(resume_file),
        },
        attempt_count=1,
        max_attempts=3,
        company_id=world.company.id,
    )
    test_db.add(durable_job)
    test_db.commit()

    # Custom mock parser returning rich content
    class MockResumeParser:
        def extract_text(self, file_path: Path) -> str:
            return """
            Ada Lovelace
            ada@example.com
            London, UK
            Skills: Python, FastAPI, Docker, Kubernetes, PostgreSQL, Algorithms
            Experience: Senior Backend Engineer at Analytic Engines (2020-Present)
            Summary: Pioneering computer scientist and backend architect.
            """

    handler = ResumeIntelligenceJobHandler(test_db, resume_parser=MockResumeParser())
    handler.execute(durable_job)

    # Refresh candidate & check enrichment
    test_db.refresh(candidate)
    assert "Python" in (candidate.skills or "")
    assert candidate.summary is not None
    assert len(candidate.summary) > 0

    # Verify ApplicationAIAnalysis record was created
    analysis = test_db.scalar(
        select(ApplicationAIAnalysis).where(ApplicationAIAnalysis.application_id == application.id)
    )
    assert analysis is not None
    assert 0 <= analysis.overall_score <= 100
    assert 0 <= analysis.skills_score <= 100
    assert analysis.summary is not None
    assert analysis.recommendation is not None
    assert analysis.confidence > 0

    # Verify ranking score calculation
    rank_score = calculate_overall_rank_score(analysis)
    assert rank_score >= 0


def test_resume_intelligence_job_handler_missing_file_raises_retryable_error(test_db: Session):
    world = PublicApplyTestWorld(test_db)

    candidate = Candidate(
        first_name="Ghost",
        last_name="Candidate",
        full_name="Ghost Candidate",
        email="ghost@example.com",
        is_active=True,
    )
    test_db.add(candidate)
    test_db.flush()

    application = Application(
        company_id=world.company.id,
        job_id=world.open_job.id,
        candidate_id=candidate.id,
        resume_path="/non/existent/path/resume.pdf",
        status="new",
        source="careers_page",
    )
    test_db.add(application)
    test_db.commit()

    durable_job = DurableJob(
        job_type=DurableJobType.RESUME_INTELLIGENCE.value,
        status=DurableJobStatus.RUNNING.value,
        payload_json={
            "application_id": str(application.id),
            "candidate_id": str(candidate.id),
            "job_id": str(world.open_job.id),
            "company_id": str(world.company.id),
            "resume_path": "/non/existent/path/resume.pdf",
        },
        attempt_count=1,
        max_attempts=3,
        company_id=world.company.id,
    )

    handler = ResumeIntelligenceJobHandler(test_db)
    with pytest.raises(JobExecutionError) as exc_info:
        handler.execute(durable_job)

    assert exc_info.value.retryable is True
    assert exc_info.value.error_code == "resume_file_not_found"
    # Ensure application state was not corrupted
    test_db.refresh(application)
    assert application.status == "new"
