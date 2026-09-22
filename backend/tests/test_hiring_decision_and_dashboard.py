from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application_status import ApplicationStatus
from app.core.auth_principals import PRINCIPAL_USER
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
from app.models.interview import Interview
from app.models.job import Job
from app.models.user import User
from app.services.dashboard_service import DashboardService
from app.services.hiring_decision_service import (
    HiringDecisionService,
    calculate_composite_score,
    determine_recommendation,
)


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


def test_calculate_composite_score_formula_and_fallbacks():
    """Verify deterministic weighting, 3-stage calculation, and normalized partial fallbacks."""
    # 1. Full 3-stages (30% fit + 35% assessment + 35% interview)
    # 0.30* 90 + 0.35 * 80 + 0.35 * 80 = 27 + 28 + 28 = 83.0
    score, status, _scores, _weights = calculate_composite_score(90.0, 80.0, 80.0)
    assert score == 83.0
    assert status == "completed"
    assert determine_recommendation(score) == "hire"

    # 2. Strong hire threshold (>= 85.0)
    # 0.30* 95 + 0.35 * 90 + 0.35 * 90 = 28.5 + 31.5 + 31.5 = 91.5
    score, status, _, _ = calculate_composite_score(95.0, 90.0, 90.0)
    assert score == 91.5
    assert status == "completed"
    assert determine_recommendation(score) == "strong_hire"

    # 3. Review threshold (55.0 - 69.9)
    score, _, _, _ = calculate_composite_score(60.0, 60.0, 60.0)
    assert score == 60.0
    assert determine_recommendation(score) == "review"

    # 4. Reject threshold (< 55.0)
    score, _, _, _ = calculate_composite_score(40.0, 40.0, 40.0)
    assert score == 40.0
    assert determine_recommendation(score) == "reject"

    # 5. Partial completion: interview pending (no division by zero)
    # fit=80.0, assessment=70.0 -> weights: 0.3 + 0.35 = 0.65
    # (0.30*80 + 0.35*70) / 0.65 = (48.5) / 0.65 = 74.6
    score, status, _, _ = calculate_composite_score(80.0, 70.0, None)
    assert score == 74.6
    assert status == "in_progress"
    assert determine_recommendation(score) == "hire"

    # 6. Zero stages completed (all None)
    score, status, _, _ = calculate_composite_score(None, None, None)
    assert score == 0.0
    assert status == "pending"
    assert determine_recommendation(score) == "reject"


def test_evaluate_final_hiring_decision_persistence(test_db: Session):
    """Verify persistence of composite_score, hiring_decision_json, and tenant isolation."""
    recruiter_user = User(
        id=uuid4(), email="recruiter@techcorp.com", hashed_password=hash_password("Secret123!"),
        full_name="Recruiter Jane", is_active=True,
    )
    test_db.add(recruiter_user)
    test_db.flush()
    company = Company(id=uuid4(), name="Tech Corp", slug="tech-corp", owner_id=recruiter_user.id, is_active=True)
    test_db.add(company)
    test_db.flush()
    member = CompanyMember(
        id=uuid4(), company_id=company.id, user_id=recruiter_user.id, role="recruiter", is_active=True,
    )
    test_db.add(member)
    test_db.flush()

    job = Job(
        id=uuid4(), company_id=company.id, company_member_id=member.id, title="Senior Software Engineer",
        description="Python FastAPI systems", department="Engineering",
        location="Remote", status="open", is_active=True,
    )
    test_db.add(job)

    candidate = Candidate(
        id=uuid4(), first_name="Alex", last_name="Tester",
        full_name="Alex Tester", email="alex@example.com",
        status="new", is_active=True,
    )
    test_db.add(candidate)

    app = Application(
        id=uuid4(), company_id=company.id, job_id=job.id, candidate_id=candidate.id,
        status="interview_completed",
        fit_score=85.0,
        assessment_score=80.0,
        interview_score=90.0,
    )
    test_db.add(app)
    test_db.commit()

    # 1. Evaluate decision
    service = HiringDecisionService(test_db)
    updated_app = service.evaluate_final_hiring_decision(app.id, company.id)

    # 0.30*85 + 0.35*80 + 0.35*90 = 25.5 + 28 + 31.5 = 85.0
    assert updated_app.composite_score == 85.0
    assert updated_app.hiring_decision_json is not None
    assert updated_app.hiring_decision_json["recommendation"] == "strong_hire"
    assert updated_app.hiring_decision_json["status"] == "completed"
    assert updated_app.status == "decision_ready"

    # 2. Cross-tenant boundary test: different company cannot evaluate or access
    with pytest.raises(LookupError, match="Application not found"):
        service.evaluate_final_hiring_decision(app.id, uuid4())


def test_dashboard_summary_multi_tenant_isolation(test_db: Session):
    """Verify dashboard summary aggregates and candidate ranking isolation across tenants."""
    # Tenant A
    user_a = User(id=uuid4(), full_name="User A", email="user_a@acme.com", hashed_password=hash_password("Secret123!"), is_active=True)
    test_db.add(user_a)
    test_db.flush()
    company_a = Company(id=uuid4(), name="Acme Corp", slug="acme-corp", owner_id=user_a.id, is_active=True)
    test_db.add(company_a)
    test_db.flush()
    member_a = CompanyMember(id=uuid4(), company_id=company_a.id, user_id=user_a.id, role="recruiter", is_active=True)
    test_db.add(member_a)
    test_db.flush()

    job_a1 = Job(id=uuid4(), company_id=company_a.id, company_member_id=member_a.id, title="Backend Eng one", status="open", is_active=True)
    job_a2 = Job(id=uuid4(), company_id=company_a.id, company_member_id=member_a.id, title="Backend Eng two", status="open", is_active=True)
    test_db.add_all([job_a1, job_a2])

    cand_a1 = Candidate(id=uuid4(), first_name="Cand1A", last_name="A", full_name="Cand1AA", email="cand1a@example.com")
    cand_a2 = Candidate(id=uuid4(), first_name="Cand2A", last_name="A", full_name="Cand2AA", email="cand2a@example.com")
    test_db.add_all([cand_a1, cand_a2])

    app_a1 = Application(
        id=uuid4(), company_id=company_a.id, job_id=job_a1.id, candidate_id=cand_a1.id,
        status="decision_ready", composite_score=92.0,
        hiring_decision_json={"recommendation": "strong_hire"},
    )
    app_a2 = Application(
        id=uuid4(), company_id=company_a.id, job_id=job_a2.id, candidate_id=cand_a2.id,
        status="interview_completed", composite_score=75.0,
        hiring_decision_json={"recommendation": "hire"},
    )
    test_db.add_all([app_a1, app_a2])

    now = datetime.now(timezone.utc)
    itv_a = Interview(
        id=uuid4(), company_id=company_a.id, application_id=app_a1.id,
        status="completed", interview_type="technical",
        scheduled_start=now, scheduled_end=now,
        timezone="UTC",
    )
    test_db.add(itv_a)

    # Tenant B (isolated)
    user_b = User(id=uuid4(), full_name="User B", email="user_b@beta.com", hashed_password=hash_password("Secret123!"), is_active=True)
    test_db.add(user_b)
    test_db.flush()
    company_b = Company(id=uuid4(), name="Beta LLC", slug="beta-llc", owner_id=user_b.id, is_active=True)
    test_db.add(company_b)
    test_db.flush()
    member_b = CompanyMember(id=uuid4(), company_id=company_b.id, user_id=user_b.id, role="recruiter", is_active=True)
    test_db.add(member_b)
    test_db.flush()

    job_b = Job(id=uuid4(), company_id=company_b.id, company_member_id=member_b.id, title="Product Manager", status="open", is_active=True)
    cand_b = Candidate(id=uuid4(), first_name="CandB", last_name="B", full_name="CandBBApp", email="candb@example.com")
    test_db.add_all([job_b, cand_b])

    app_b = Application(
        id=uuid4(), company_id=company_b.id, job_id=job_b.id, candidate_id=cand_b.id,
        status="screening", composite_score=99.0,
    )
    test_db.add(app_b)
    test_db.commit()

    # Run DashboardService for Company A
    dashboard_service = DashboardService(db=test_db)
    summary_a = dashboard_service.get_dashboard_summary(company_a.id)

    assert summary_a["kpis"]["total_candidates"] == 2
    assert summary_a["kpis"]["active_jobs"] == 2
    assert summary_a["kpis"]["interviews_completed"] == 1
    assert summary_a["kpis"]["pending_decisions"] == 2
    assert len(summary_a["top_candidates"]) == 2
    assert summary_a["top_candidates"][0]["rank"] == 1
    assert summary_a["top_candidates"][0]["composite_score"] == 92.0
    assert summary_a["top_candidates"][1]["rank"] == 2
    assert summary_a["top_candidates"][1]["composite_score"] == 75.0

    # Company B candidate (composite_score=99.0) must NOT appear in Company A's top candidates!
    for cand in summary_a["top_candidates"]:
        assert cand["candidate_id"] != str(cand_b.id)

    # Tenant with 0 jobs and 0 candidates (edge case returns valid zeros)
    empty_company_id = uuid4()
    empty_summary = dashboard_service.get_dashboard_summary(empty_company_id)
    assert empty_summary["kpis"]["total_candidates"] == 0
    assert empty_summary["kpis"]["active_jobs"] == 0
    assert empty_summary["top_candidates"] == []


def test_dashboard_summary_and_hiring_decision_api_routes(test_db: Session):
    """Verify GET /api/v1/dashboard/summary, /dashboard/summary, and hiring-decision evaluation."""
    recruiter_user = User(
        id=uuid4(), email="omega_recruiter@omega.com", hashed_password=hash_password("Secret123!"),
        full_name="Omega Recruiter", is_active=True,
    )
    test_db.add(recruiter_user)
    test_db.flush()
    company = Company(id=uuid4(), name="Omega Corp", slug="omega-corp", owner_id=recruiter_user.id, is_active=True)
    test_db.add(company)
    test_db.flush()
    member = CompanyMember(
        id=uuid4(), company_id=company.id, user_id=recruiter_user.id, role="recruiter", is_active=True,
    )
    test_db.add(member)
    test_db.flush()

    job = Job(id=uuid4(), company_id=company.id, company_member_id=member.id, title="Full Stack", status="open", is_active=True)
    cand = Candidate(id=uuid4(), first_name="Sam", last_name="Omega", full_name="Sam Omega", email="sam@omega.com")
    test_db.add_all([job, cand])

    app = Application(
        id=uuid4(), company_id=company.id, job_id=job.id, candidate_id=cand.id,
        status="interview_completed", fit_score=80.0, assessment_score=75.0, interview_score=85.0,
    )
    test_db.add(app)
    test_db.commit()

    def _override_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = _override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: recruiter_user

    token = create_access_token(recruiter_user.id, principal=PRINCIPAL_USER)
    client = TestClient(fastapi_app)
    client.headers.update({"Authorization": f"Bearer {token}"})

    # 1. GET /api/v1/dashboard/summary
    res_v1 = client.get("/api/v1/dashboard/summary")
    assert res_v1.status_code == 200, res_v1.text
    data_v1 = res_v1.json()
    assert "kpis" in data_v1
    assert "pipeline_overview" in data_v1
    assert "top_candidates" in data_v1

    # 2. GET /dashboard/summary
    res_root = client.get("/dashboard/summary")
    assert res_root.status_code == 200, res_root.text

    # 3. POST /api/v1/applications/{app_id}/hiring-decision
    dec_res = client.post(f"/api/v1/applications/{app.id}/hiring-decision")
    assert dec_res.status_code == 200, dec_res.text
    dec_data = dec_res.json()
    assert dec_data["status"] == "decision_ready"
    assert dec_data["composite_score"] > 0


    fastapi_app.dependency_overrides.clear()


def test_notifications_api_routes_and_proxy_support(test_db: Session):
    """Verify notifications endpoints return valid JSON 200 OK on /api/v1/notifications, /notifications, and /api/notifications."""
    recruiter = User(
        id=uuid4(), full_name="Notif Recruiter", email="notif_recruiter@notif.com", hashed_password=hash_password("Secret123!"),
        is_active=True,
    )
    test_db.add(recruiter)
    test_db.flush()
    company = Company(id=uuid4(), name="Notif Corp", slug="notif-corp", owner_id=recruiter.id, is_active=True)
    test_db.add(company)
    test_db.flush()
    member = CompanyMember(
        id=uuid4(), company_id=company.id, user_id=recruiter.id, role="recruiter", is_active=True,
    )
    test_db.add(member)
    test_db.commit()

    fastapi_app.dependency_overrides[get_db] = lambda: test_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: recruiter

    token = create_access_token(recruiter.id, principal=PRINCIPAL_USER)
    client = TestClient(fastapi_app)
    client.headers.update({"Authorization": f"Bearer {token}"})

    # 1. GET /api/v1/notifications
    res_v1 = client.get("/api/v1/notifications")
    assert res_v1.status_code == 200, res_v1.text
    assert "application/json" in res_v1.headers["content-type"]
    v1_data = res_v1.json()
    assert "items" in v1_data
    assert "unread_count" in v1_data

    # 2. GET /notifications
    res_root = client.get("/notifications")
    assert res_root.status_code == 200, res_root.text
    assert "application/json" in res_root.headers["content-type"]

    # 3. GET /api/notifications
    res_api = client.get("/api/notifications")
    assert res_api.status_code == 200, res_api.text
    assert "application/json" in res_api.headers["content-type"]


    fastapi_app.dependency_overrides.clear()
