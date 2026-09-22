"""Comprehensive End-to-End Recruitment Lifecycle Integration Test.

Validates the full sequential lifecycle:
1. Public candidate application intake & resume upload -> Application in 'applied' status.
2. Background AI Resume Intelligence worker execution -> skills extracted, fit_score persisted, status moves to 'screening'.
3. Candidate Portal AI pre-screening MCQ assessment -> auto-scoring, assessment_score stored.
4. Candidate Portal AI structured interview session -> answers submitted, interview_score stored, status moves to 'interview_completed'.
5. AI Hiring Decision Engine -> weighted composite_score and recommendation computed, status moves to 'decision_ready'.
6. Recruiter updates candidate stage to 'offered' (and 'hired') directly -> state persisted to PostgreSQL.
7. Recruiter Dashboard summary reflects live candidate metrics and top-ranked candidate.
8. Edge cases: Cross-tenant unauthorized transition rejection, and empty-company analytics zeroed metrics.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.pipelines.assessment_generation import generate_fallback_assessment
from app.core.application_status import ApplicationStatus
from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.durable_job import DurableJobStatus, DurableJobType
from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app as fastapi_app
import app.models  # noqa: F401
from app.models.application import Application
from app.models.application_ai_analysis import ApplicationAIAnalysis
from app.models.assessment import AssessmentSession
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.durable_job import DurableJob
from app.models.interview import Interview, InterviewSession
from app.models.job import Job
from app.models.user import User
from app.repositories.candidate import CandidateRepository
from app.services.ai_interview_service import AIInterviewService
from app.services.assessment_service import AssessmentService
from app.services.dashboard_service import DashboardService
from app.services.hiring_decision_service import HiringDecisionService
from app.services.job_handlers.resume_intelligence import ResumeIntelligenceJobHandler


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


class LifecycleWorld:
    def __init__(self, db: Session, tmp_path: Path) -> None:
        self.db = db
        self.tmp_path = tmp_path

        # 1. Recruiter User
        self.recruiter = User(
            id=uuid4(),
            full_name="Sarah Connor",
            email="sarah@skynet-recruitment.com",
            hashed_password=hash_password("SuperSecret123!"),
            is_active=True,
            role="recruiter",
        )
        self.db.add(self.recruiter)
        self.db.flush()

        # 2. Tenant Company
        self.company = Company(
            id=uuid4(),
            name="Cyberdyne Systems",
            slug=f"cyberdyne-{uuid4().hex[:6]}",
            owner_id=self.recruiter.id,
            is_active=True,
        )
        self.db.add(self.company)
        self.db.flush()

        # 3. Recruiter Company Membership
        self.member = CompanyMember(
            id=uuid4(),
            company_id=self.company.id,
            user_id=self.recruiter.id,
            role="recruiter",
            is_active=True,
        )
        self.db.add(self.member)
        self.db.flush()

        # 4. Published Job Posting
        self.job = Job(
            id=uuid4(),
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.recruiter.id,
            title="Senior Distributed Systems Engineer",
            department="Core Infrastructure",
            location="Remote",
            employment_type="full_time",
            experience_level="Senior",
            description="Build ultra high-throughput distributed services with Python, FastAPI, and PostgreSQL.",
            job_intelligence={"required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"]},
            status="open",
            is_active=True,
        )
        self.db.add(self.job)
        self.db.commit()


def test_full_recruitment_lifecycle_end_to_end(test_db: Session, tmp_path: Path):
    """End-to-End integration test covering Candidate Intake -> Resume Parsing -> Assessment -> Interview -> Hiring Decision -> Offer Stage -> Dashboard Reflection."""
    world = LifecycleWorld(test_db, tmp_path)

    def _override_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: world.recruiter
    client = TestClient(fastapi_app)

    # -------------------------------------------------------------------------
    # STEP 1: Candidate Public Intake & Resume Upload
    # -------------------------------------------------------------------------
    resume_text = (
        "MORGAN STARK\nSenior Backend & Cloud Architect\n\n"
        "Summary:\nSpecialist in high-throughput backend services using Python, FastAPI, and relational databases.\n\n"
        "Technical Skills:\nPython, FastAPI, PostgreSQL, Docker, Kubernetes, Microservices, Redis, Git\n\n"
        "Professional Experience:\n"
        "Lead Infrastructure Engineer at Stark Labs (2020-Present)\n"
        "Designed and maintained resilient FastAPI event microservices with PostgreSQL on Kubernetes.\n"
    )
    dummy_pdf = b"%PDF-1.4 Morgan Stark Senior Backend Engineer"
    files = {"resume": ("morgan_stark_resume.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    data = {
        "full_name": "Morgan Stark",
        "email": "morgan.stark@starklabs.com",
        "phone": "+1-555-0142",
    }

    apply_res = client.post(f"/public/jobs/{world.job.id}/apply", data=data, files=files)
    assert apply_res.status_code == 201, apply_res.text
    apply_payload = apply_res.json()
    assert apply_payload["job_id"] == str(world.job.id)
    assert apply_payload["status"] == "applied"
    application_id = UUID(apply_payload["application_id"])

    # Verify database state after Step 1
    application = test_db.scalar(select(Application).where(Application.id == application_id))
    assert application is not None
    assert application.status == ApplicationStatus.APPLIED.value
    assert application.company_id == world.company.id

    candidate = test_db.scalar(select(Candidate).where(Candidate.email == "morgan.stark@starklabs.com"))
    assert candidate is not None
    assert candidate.full_name == "Morgan Stark"
    assert candidate.latest_application is not None
    assert candidate.latest_application.id == application.id

    # Verify background durable job enqueued
    durable_job = test_db.scalar(
        select(DurableJob).where(
            DurableJob.job_type == DurableJobType.RESUME_INTELLIGENCE.value,
            DurableJob.company_id == world.company.id,
        )
    )
    assert durable_job is not None
    assert durable_job.status == DurableJobStatus.PENDING.value

    # -------------------------------------------------------------------------
    # STEP 2: Durable Resume Intelligence Worker Execution
    # -------------------------------------------------------------------------
    class MockResumeParser:
        def extract_text(self, file_path: Path) -> str:
            return resume_text

    handler = ResumeIntelligenceJobHandler(test_db, resume_parser=MockResumeParser())
    handler.execute(durable_job)

    test_db.refresh(application)
    test_db.refresh(candidate)
    assert application.fit_score is not None
    assert application.fit_score > 0
    assert application.status in [ApplicationStatus.SCREENING.value, ApplicationStatus.SHORTLISTED.value]
    assert candidate.fit_score == application.fit_score

    ai_analysis = test_db.scalar(select(ApplicationAIAnalysis).where(ApplicationAIAnalysis.application_id == application.id))
    assert ai_analysis is not None
    assert len(ai_analysis.matched_skills) > 0

    # -------------------------------------------------------------------------
    # STEP 3: Candidate Portal AI Pre-Screening Assessment (MCQ Auto-Scoring)
    # -------------------------------------------------------------------------
    assessment_service = AssessmentService(test_db)
    assessment_session = assessment_service.get_or_create_session(application.id, candidate)
    assert assessment_session.status == "pending"
    assert len(assessment_session.questions_json) >= 5

    # Submit 5 out of 5 correct answers (100% score)
    questions = assessment_session.questions_json
    answers = {q["id"]: q["correct_option"] for q in questions}

    submit_assess_res = assessment_service.submit_candidate_assessment(application.id, candidate, answers)
    assert submit_assess_res.status == "completed"
    assert submit_assess_res.score == 100.0
    assert submit_assess_res.passed is True

    test_db.refresh(application)
    assert application.assessment_score == 100.0

    # -------------------------------------------------------------------------
    # STEP 4: Candidate Portal AI Structured Interview Session
    # -------------------------------------------------------------------------
    interview_service = AIInterviewService(test_db)
    interview_session_data = interview_service.get_candidate_interview(application.id, candidate)
    assert interview_session_data.application_id == application.id
    assert interview_session_data.status == "pending"
    assert len(interview_session_data.questions) >= 3

    interview_answers = {
        q.id: f"Engineered scalable microservices in Python with robust distributed locking and metrics for {q.competency}."
        for q in interview_session_data.questions
    }
    submit_interview_res = interview_service.submit_candidate_interview(application.id, candidate, interview_answers)
    assert submit_interview_res.status == "completed"
    assert submit_interview_res.score > 0
    assert submit_interview_res.recommendation in ["hire", "strong_hire"]

    test_db.refresh(application)
    assert application.interview_score == submit_interview_res.score

    # -------------------------------------------------------------------------
    # STEP 5: AI Hiring Decision Engine (Weighted Composite Scoring)
    # -------------------------------------------------------------------------
    decision_service = HiringDecisionService(test_db)
    evaluated_app = decision_service.evaluate_final_hiring_decision(application.id, world.company.id)

    # 30% Fit + 35% Assessment + 35% Interview
    expected_score = round(0.30 * application.fit_score + 0.35 * 100.0 + 0.35 * application.interview_score, 1)
    assert evaluated_app.composite_score == expected_score
    assert evaluated_app.hiring_decision_json is not None
    assert evaluated_app.hiring_decision_json["recommendation"] in ["strong_hire", "hire"]
    assert evaluated_app.status == ApplicationStatus.DECISION_READY.value

    # -------------------------------------------------------------------------
    # STEP 6: Recruiter Advances Candidate Stage to 'offered' and 'hired'
    # -------------------------------------------------------------------------
    recruiter_token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
    recruiter_client = TestClient(fastapi_app)
    recruiter_client.headers.update({"Authorization": f"Bearer {recruiter_token}"})

    # Transition to 'offered'
    offer_patch_res = recruiter_client.patch(
        f"/api/v1/applications/{application.id}/status",
        json={"status": "offered"},
    )
    assert offer_patch_res.status_code == 200, offer_patch_res.text
    offer_data = offer_patch_res.json()
    assert offer_data["status"] == "offered"

    test_db.refresh(application)
    assert application.status == ApplicationStatus.OFFERED.value

    # Transition to 'hired'
    hire_patch_res = recruiter_client.patch(
        f"/api/v1/applications/{application.id}/status",
        json={"status": "hired"},
    )
    assert hire_patch_res.status_code == 200, hire_patch_res.text
    assert hire_patch_res.json()["status"] == "hired"

    test_db.refresh(application)
    assert application.status == ApplicationStatus.HIRED.value

    # -------------------------------------------------------------------------
    # STEP 7: Live Recruiter Dashboard Reflects Candidate in KPIs and Stack Ranking
    # -------------------------------------------------------------------------
    dash_res = recruiter_client.get("/api/v1/dashboard/summary")
    assert dash_res.status_code == 200, dash_res.text
    dash_data = dash_res.json()

    assert dash_data["kpis"]["total_candidates"] == 1
    assert dash_data["kpis"]["active_jobs"] == 1
    assert dash_data["kpis"]["interviews_completed"] >= 1
    assert len(dash_data["top_candidates"]) == 1

    top_cand = dash_data["top_candidates"][0]
    assert top_cand["rank"] == 1
    assert top_cand["candidate_name"] == "Morgan Stark"
    assert top_cand["application_id"] == str(application.id)
    assert top_cand["composite_score"] == expected_score


def test_cross_tenant_status_transition_isolation(test_db: Session, tmp_path: Path):
    """Verify recruiter from Tenant B cannot modify application status of Tenant A."""
    world_a = LifecycleWorld(test_db, tmp_path)

    # Setup Tenant B
    recruiter_b = User(
        id=uuid4(), full_name="Intruder Bob", email="bob@othercorp.com",
        hashed_password=hash_password("Secret123!"), is_active=True, role="recruiter",
    )
    test_db.add(recruiter_b)
    test_db.flush()

    company_b = Company(
        id=uuid4(), name="Other Corp", slug=f"other-{uuid4().hex[:6]}",
        owner_id=recruiter_b.id, is_active=True,
    )
    test_db.add(company_b)
    test_db.flush()

    member_b = CompanyMember(
        id=uuid4(), company_id=company_b.id, user_id=recruiter_b.id,
        role="recruiter", is_active=True,
    )
    test_db.add(member_b)
    test_db.commit()

    # Create an application in Tenant A
    cand_a = Candidate(
        id=uuid4(), first_name="Alice", last_name="A", full_name="Alice A",
        email="alice@acme.com", status="new", is_active=True,
    )
    test_db.add(cand_a)
    test_db.flush()

    app_a = Application(
        id=uuid4(), company_id=world_a.company.id, job_id=world_a.job.id,
        candidate_id=cand_a.id, status="decision_ready",
    )
    test_db.add(app_a)
    test_db.commit()

    # Recruiter B attempts to update Tenant A's application
    def _override_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: recruiter_b
    client_b = TestClient(fastapi_app)
    token_b = create_access_token(recruiter_b.id, principal=PRINCIPAL_USER)
    client_b.headers.update({"Authorization": f"Bearer {token_b}"})

    patch_res = client_b.patch(f"/api/v1/applications/{app_a.id}/status", json={"status": "offered"})
    assert patch_res.status_code in [403, 404]

    # Database record for Tenant A must remain untouched
    test_db.refresh(app_a)
    assert app_a.status == "decision_ready"

    fastapi_app.dependency_overrides.clear()


def test_empty_company_analytics_and_dashboard_stability(test_db: Session):
    """Verify querying dashboard summary and analytics widgets for an empty company returns valid zeroed JSON without crashing."""
    empty_company = Company(
        id=uuid4(), name="Zero Corp", slug=f"zero-{uuid4().hex[:6]}",
        owner_id=uuid4(), is_active=True,
    )
    # create user owner
    owner = User(
        id=empty_company.owner_id, full_name="Zero Owner", email="owner@zero.com",
        hashed_password=hash_password("Pass123!"), is_active=True,
    )
    test_db.add(owner)
    test_db.flush()
    test_db.add(empty_company)
    test_db.commit()

    service = DashboardService(db=test_db)
    summary = service.get_dashboard_summary(empty_company.id)

    assert summary["kpis"]["total_candidates"] == 0
    assert summary["kpis"]["active_jobs"] == 0
    assert summary["kpis"]["interviews_completed"] == 0
    assert summary["kpis"]["pending_decisions"] == 0
    assert summary["top_candidates"] == []

    # Widgets
    pipeline_w = service.get_pipeline_widget(empty_company.id)
    assert pipeline_w["total_in_pipeline"] == 0
    assert isinstance(pipeline_w["pipeline_stages"], dict)

    funnel_w = service.get_funnel_widget(empty_company.id)
    assert funnel_w["total"] == 0

    jobs_w = service.get_job_statistics_widget(empty_company.id)
    assert jobs_w["total_jobs"] == 0

    interviews_w = service.get_interview_metrics_widget(empty_company.id)
    assert interviews_w["interview_sessions"] == 0
