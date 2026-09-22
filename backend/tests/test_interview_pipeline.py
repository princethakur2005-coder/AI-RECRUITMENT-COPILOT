from __future__ import annotations

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.pipelines.interview_evaluation import (
    InterviewEvaluationPipeline,
    evaluate_answers_deterministically,
)
from app.ai.pipelines.interview_generation import (
    InterviewGenerationPipeline,
    generate_fallback_interview,
)
from app.core.application_status import ApplicationStatus
from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app as fastapi_app
import app.models  # noqa: F401
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.interview import Interview, InterviewSession
from app.models.interview_ai_analysis import InterviewAIAnalysis
from app.models.job import Job
from app.models.user import User
from app.repositories.candidate import CandidateRepository
from app.services.ai_interview_service import AIInterviewService


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


class InterviewTestFixture:
    def __init__(self, db: Session) -> None:
        self.db = db

        self.recruiter_user = User(
            id=uuid4(),
            email="recruiter@acme.com",
            hashed_password=hash_password("Secret123!"),
            full_name="Recruiter Alice",
            is_active=True,
        )
        self.db.add(self.recruiter_user)
        self.db.flush()

        self.company = Company(
            id=uuid4(),
            name="Acme Corp",
            slug="acme-corp",
            owner_id=self.recruiter_user.id,
            is_active=True,
        )
        self.db.add(self.company)
        self.db.flush()

        self.member = CompanyMember(
            id=uuid4(),
            company_id=self.company.id,
            user_id=self.recruiter_user.id,
            role="recruiter",
        )
        self.db.add(self.member)
        self.db.flush()

        self.job = Job(
            id=uuid4(),
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.recruiter_user.id,
            title="Senior Backend Engineer",
            department="Engineering",
            description="Build scalable distributed services with Python and FastAPI.",
            status="published",
        )
        self.db.add(self.job)

        self.candidate = Candidate(
            id=uuid4(),
            email="candidate@example.com",
            hashed_password=hash_password("CandidatePass123!"),
            first_name="John",
            last_name="Doe",
            full_name="John Doe",
            skills="Python, FastAPI, PostgreSQL, Distributed Systems",
            is_active=True,
        )
        self.db.add(self.candidate)

        self.other_candidate = Candidate(
            id=uuid4(),
            email="intruder@example.com",
            hashed_password=hash_password("IntruderPass123!"),
            first_name="Intruder",
            last_name="Eve",
            full_name="Intruder Eve",
            is_active=True,
        )
        self.db.add(self.other_candidate)

        self.application = Application(
            id=uuid4(),
            company_id=self.company.id,
            job_id=self.job.id,
            candidate_id=self.candidate.id,
            status=ApplicationStatus.SCREENING,
            assessment_score=85.0,
        )
        self.db.add(self.application)
        self.db.commit()


def test_interview_generation_pipeline_fallback():
    """Verify interview generation produces 3-5 structured role-tailored questions."""
    pipeline = InterviewGenerationPipeline()
    result = pipeline.generate(
        job_title="Senior Backend Engineer",
        job_description="Distributed systems with FastAPI and PostgreSQL",
    )
    assert result.data is not None
    questions = result.data.get("questions", [])
    assert len(questions) >= 3
    for q in questions:
        assert "id" in q
        assert "question" in q
        assert "category" in q
        assert "competency" in q


def test_interview_evaluation_pipeline_scoring():
    """Verify evaluation pipeline grades candidate responses comprehensively."""
    pipeline = InterviewEvaluationPipeline()
    questions = generate_fallback_interview("Senior Backend Engineer")
    answers = {
        "iq_1": "I designed an event-driven architecture with Kafka and PostgreSQL, choosing eventual consistency for writes and partition-aware cache invalidation.",
        "iq_2": "During a connection pool starvation outage, I analyzed slow query logs, identified unindexed table scans, and deployed connection throttling.",
        "iq_3": "When a teammate insisted on synchronous RPC calls, I benchmarked p99 latency impacts and demonstrated that asynchronous events mitigated cascading failures.",
        "iq_4": "I coordinated with product leads to defer non-blocking features, prioritizing security hotfixes while maintaining on-time core delivery.",
    }

    result = pipeline.evaluate(
        questions=questions,
        answers=answers,
        job_title="Senior Backend Engineer",
    )
    data = result.data
    assert data["score"] >= 70.0
    assert data["recommendation"] in ["hire", "strong_hire"]
    assert len(data["key_strengths"]) > 0
    assert len(data["growth_areas"]) > 0
    assert len(data["overall_feedback"]) > 0


def test_interview_service_candidate_isolation(test_db: Session):
    """Verify candidate cannot view or submit another candidate's interview."""
    fixture = InterviewTestFixture(test_db)
    service = AIInterviewService(test_db)

    with pytest.raises(LookupError, match="Application not found or unauthorized"):
        service.get_candidate_interview(fixture.application.id, fixture.other_candidate)

    with pytest.raises(LookupError, match="Application not found or unauthorized"):
        service.submit_candidate_interview(
            fixture.application.id, fixture.other_candidate, {"iq_1": "Answer"}
        )


def test_interview_service_lifecycle_and_persistence(test_db: Session):
    """Verify candidate interview flow: get questions, submit answers, persist score and transition status."""
    fixture = InterviewTestFixture(test_db)
    service = AIInterviewService(test_db)

    # 1. Fetch interview session (creates if not exists)
    resp = service.get_candidate_interview(fixture.application.id, fixture.candidate)
    assert resp.application_id == fixture.application.id
    assert resp.status == "pending"
    assert len(resp.questions) >= 3
    assert resp.score is None

    # 2. Submit answers
    answers = {
        q.id: f"Comprehensive technical answer detailing architecture and implementation for {q.competency} with thorough metrics and retrospectives."
        for q in resp.questions
    }

    submit_resp = service.submit_candidate_interview(
        fixture.application.id, fixture.candidate, answers
    )
    assert submit_resp.status == "completed"
    assert submit_resp.score > 0
    assert submit_resp.recommendation in ["hire", "strong_hire", "hold"]
    assert len(submit_resp.key_strengths) > 0

    # 3. Verify Application persistence
    test_db.refresh(fixture.application)
    assert fixture.application.interview_score == submit_resp.score
    assert fixture.application.status == "interview_completed"

    # 4. Verify Interview record was created and updated
    itv = test_db.query(Interview).filter_by(application_id=fixture.application.id).first()
    assert itv is not None
    assert itv.status == "completed"
    assert itv.interview_score == submit_resp.score
    assert itv.answers_json == answers
    assert itv.evaluation_json is not None

    # 5. Verify InterviewAIAnalysis record was created
    ai_analysis = test_db.query(InterviewAIAnalysis).filter_by(interview_id=itv.id).first()
    assert ai_analysis is not None
    assert ai_analysis.overall_score == int(round(submit_resp.score))

    # 6. Verify Candidate property
    cand = CandidateRepository(test_db).get_by_id(fixture.candidate.id)
    assert cand is not None
    assert cand.interview_score == submit_resp.score
    assert cand.interview_feedback is not None

    # 7. Resubmission must fail with ValueError (idempotent submission prevention)
    with pytest.raises(ValueError, match="Interview has already been completed"):
        service.submit_candidate_interview(
            fixture.application.id, fixture.candidate, answers
        )


def test_recruiter_and_candidate_portal_api_endpoints(test_db: Session):
    """Verify GET /api/v1/interviews returns 200 OK (no 404) and candidate portal endpoints function via HTTP."""
    fixture = InterviewTestFixture(test_db)

    def _override_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: fixture.recruiter_user

    # 1. Recruiter GET /api/v1/interviews (verify no 404!)
    recruiter_token = create_access_token(fixture.recruiter_user.id, principal=PRINCIPAL_USER)
    recruiter_client = TestClient(fastapi_app)
    recruiter_client.headers.update({"Authorization": f"Bearer {recruiter_token}"})

    res_v1 = recruiter_client.get("/api/v1/interviews")
    assert res_v1.status_code == 200, res_v1.text
    assert isinstance(res_v1.json(), list)

    res_root = recruiter_client.get("/interviews")
    assert res_root.status_code == 200, res_root.text
    assert isinstance(res_root.json(), list)

    # 2. Candidate GET interview via /api/v1/candidate/...
    cand_token = create_access_token(fixture.candidate.id, principal=PRINCIPAL_CANDIDATE)
    candidate_client = TestClient(fastapi_app)
    candidate_client.headers.update({"Authorization": f"Bearer {cand_token}"})

    get_res = candidate_client.get(f"/api/v1/candidate/applications/{fixture.application.id}/interview")
    assert get_res.status_code == 200, get_res.text
    data = get_res.json()
    assert data["application_id"] == str(fixture.application.id)
    assert data["status"] == "pending"
    assert len(data["questions"]) >= 3

    # Also check /candidate/applications/... without prefix
    legacy_res = candidate_client.get(f"/candidate/applications/{fixture.application.id}/interview")
    assert legacy_res.status_code == 200

    # 3. Candidate POST submit answers
    answers = {
        q["id"]: f"Detailed technical solution addressing {q.get('competency', 'engineering')} with comprehensive metrics and tradeoffs."
        for q in data["questions"]
    }
    submit_res = candidate_client.post(
        f"/api/v1/candidate/applications/{fixture.application.id}/interview/submit",
        json={"answers": answers},
    )
    assert submit_res.status_code == 200, submit_res.text
    submit_data = submit_res.json()
    assert submit_data["status"] == "completed"
    assert submit_data["score"] > 0
    assert submit_data["overall_feedback"]

    # 4. Re-submission attempt returns 400 Bad Request
    resubmit_res = candidate_client.post(
        f"/api/v1/candidate/applications/{fixture.application.id}/interview/submit",
        json={"answers": answers},
    )
    assert resubmit_res.status_code == 400
    assert "already been completed" in resubmit_res.json()["detail"]

    # 5. Recruiter listing now includes the completed interview
    list_after = recruiter_client.get("/api/v1/interviews")
    assert list_after.status_code == 200
    interviews_list = list_after.json()
    assert len(interviews_list) >= 1
    ai_interview = next(
        (itv for itv in interviews_list if itv["application_id"] == str(fixture.application.id)),
        None,
    )
    assert ai_interview is not None
    assert ai_interview["status"] == "completed"
    assert ai_interview["interview_score"] == submit_data["score"]

    # 6. Recruiter candidate detail includes interview_score and feedback
    cand_detail = recruiter_client.get(f"/candidates/{fixture.candidate.id}")
    assert cand_detail.status_code == 200
    cand_data = cand_detail.json()
    assert cand_data["interview_score"] == submit_data["score"]
    assert cand_data["interview_feedback"] is not None

    fastapi_app.dependency_overrides.clear()
