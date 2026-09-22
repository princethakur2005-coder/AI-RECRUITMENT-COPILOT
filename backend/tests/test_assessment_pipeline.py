from __future__ import annotations

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.pipelines.assessment_generation import (
    AssessmentGenerationPipeline,
    generate_fallback_assessment,
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
from app.models.assessment import AssessmentSession
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.job import Job
from app.models.user import User
from app.repositories.candidate import CandidateRepository
from app.services.assessment_service import AssessmentService


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


class AssessmentTestFixture:
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
            description="Develop high throughput distributed backend systems in Python and FastAPI.",
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
            skills="Python, FastAPI, PostgreSQL, Docker",
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
            status=ApplicationStatus.APPLIED,
        )
        self.db.add(self.application)

        self.db.commit()


def test_assessment_generation_pipeline_fallback():
    """Verify generation pipeline produces valid 5 questions with options and answer keys."""
    pipeline = AssessmentGenerationPipeline()
    assessment = pipeline.generate_assessment(
        job_title="Senior Backend Engineer",
        department="Engineering",
        job_description="Build distributed services with Python",
        candidate_skills="Python, Microservices",
        question_count=5,
    )

    assert "questions" in assessment
    questions = assessment["questions"]
    assert len(questions) == 5

    for q in questions:
        assert "id" in q
        assert "question" in q
        assert "options" in q
        assert set(q["options"].keys()) == {"A", "B", "C", "D"}
        assert q["correct_option"] in {"A", "B", "C", "D"}
        assert "difficulty" in q
        assert "skill_tag" in q
        assert "explanation" in q


def test_assessment_service_get_and_redaction(test_db: Session):
    """Verify candidate assessment strictly redacts correct answers and explanation."""
    fixture = AssessmentTestFixture(test_db)
    service = AssessmentService(test_db)

    res = service.get_candidate_assessment(fixture.application.id, fixture.candidate)
    assert res.application_id == fixture.application.id
    assert res.status == "pending"
    assert res.total_questions == 5
    assert len(res.questions) == 5

    # Strictly check that correct_option and explanation are NOT present in questions
    for q in res.questions:
        q_dict = q.model_dump()
        assert "correct_option" not in q_dict
        assert "explanation" not in q_dict
        assert q.options
        assert len(q.options) == 4


def test_assessment_service_isolation(test_db: Session):
    """Verify other candidate cannot access or submit another candidate's assessment."""
    fixture = AssessmentTestFixture(test_db)
    service = AssessmentService(test_db)

    with pytest.raises(LookupError, match="Application not found"):
        service.get_candidate_assessment(fixture.application.id, fixture.other_candidate)


def test_assessment_submission_and_auto_scoring(test_db: Session):
    """Verify candidate submission calculates score, stores breakdown, updates application, and prevents resubmission."""
    fixture = AssessmentTestFixture(test_db)
    service = AssessmentService(test_db)

    # Initialize session
    session = service.get_or_create_session(fixture.application.id, fixture.candidate)
    assert session.status == "pending"

    # Submit 4 correct answers out of 5 (80%)
    questions = session.questions_json
    answers = {}
    for i, q in enumerate(questions):
        if i < 4:
            answers[q["id"]] = q["correct_option"]
        else:
            wrong_opt = "A" if q["correct_option"] != "A" else "B"
            answers[q["id"]] = wrong_opt

    submit_res = service.submit_candidate_assessment(fixture.application.id, fixture.candidate, answers)
    assert submit_res.status == "completed"
    assert submit_res.score == 80.0
    assert submit_res.correct_count == 4
    assert submit_res.total_questions == 5
    assert submit_res.passed is True
    assert len(submit_res.breakdown["details"]) == 5

    # Check database persistence
    test_db.refresh(fixture.application)
    assert fixture.application.assessment_score == 80.0
    assert fixture.application.status == ApplicationStatus.SCREENING

    # Test Candidate property
    cand = CandidateRepository(test_db).get_by_id(fixture.candidate.id)
    assert cand is not None
    assert cand.assessment_score == 80.0
    assert cand.assessment_breakdown is not None
    assert cand.assessment_breakdown["score"] == 80.0

    # Idempotency / resubmission rejection
    with pytest.raises(ValueError, match="Assessment has already been submitted"):
        service.submit_candidate_assessment(fixture.application.id, fixture.candidate, answers)


def test_candidate_portal_assessment_api_endpoints(test_db: Session):
    """Test GET /api/v1/candidate/applications/{id}/assessment and POST submit endpoints via HTTP client."""
    fixture = AssessmentTestFixture(test_db)

    def _override_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: fixture.recruiter_user

    cand_token = create_access_token(fixture.candidate.id, principal=PRINCIPAL_CANDIDATE)
    client = TestClient(fastapi_app)
    client.headers.update({"Authorization": f"Bearer {cand_token}"})

    # 1. GET assessment via /api/v1/candidate/...
    get_res = client.get(f"/api/v1/candidate/applications/{fixture.application.id}/assessment")
    assert get_res.status_code == 200, get_res.text
    data = get_res.json()
    assert data["application_id"] == str(fixture.application.id)
    assert data["status"] == "pending"
    assert len(data["questions"]) == 5

    # Verify no leaked answer keys in response
    for q in data["questions"]:
        assert "correct_option" not in q
        assert "explanation" not in q

    # 2. Also verify /candidate/... without /api/v1 prefix works
    legacy_get_res = client.get(f"/candidate/applications/{fixture.application.id}/assessment")
    assert legacy_get_res.status_code == 200

    # 3. POST submit answers
    # Submit all correct answers
    raw_session = test_db.query(AssessmentSession).filter_by(application_id=fixture.application.id).first()
    assert raw_session is not None
    all_correct = {q["id"]: q["correct_option"] for q in raw_session.questions_json}

    post_res = client.post(
        f"/api/v1/candidate/applications/{fixture.application.id}/assessment/submit",
        json={"answers": all_correct},
    )
    assert post_res.status_code == 200, post_res.text
    submit_data = post_res.json()
    assert submit_data["status"] == "completed"
    assert submit_data["score"] == 100.0
    assert submit_data["correct_count"] == 5
    assert submit_data["passed"] is True

    # 4. Resubmit should fail with 400
    resubmit_res = client.post(
        f"/api/v1/candidate/applications/{fixture.application.id}/assessment/submit",
        json={"answers": all_correct},
    )
    assert resubmit_res.status_code == 400
    assert "already been submitted" in resubmit_res.json()["detail"]

    # 5. Check recruiter candidate endpoint has assessment_score
    recruiter_client = TestClient(fastapi_app)
    recruiter_token = create_access_token(fixture.recruiter_user.id, principal=PRINCIPAL_USER)
    recruiter_client.headers.update({"Authorization": f"Bearer {recruiter_token}"})

    cand_detail_res = recruiter_client.get(f"/candidates/{fixture.candidate.id}")
    assert cand_detail_res.status_code == 200
    cand_json = cand_detail_res.json()
    assert cand_json["assessment_score"] == 100.0
    assert cand_json["assessment_breakdown"] is not None

    fastapi_app.dependency_overrides.clear()

