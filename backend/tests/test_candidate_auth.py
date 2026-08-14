"""Candidate authentication/identity foundation tests."""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import create_access_token, verify_access_token
from app.core.security import hash_password
from app.db.base import Base
from app.db.database import get_db
from app.dependencies.auth import require_candidate_self
from app.main import app
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.company_member import CompanyMember
from app.models.job import Job
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.schemas.public_apply import PublicApplyForm
from app.services.public_apply import PublicApplyService


@pytest.fixture
def auth_db() -> Session:
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


class CandidateAuthWorld:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.owner = User(
            full_name="Owner",
            email="owner@acme.test",
            hashed_password=hash_password("OwnerPass1!"),
            role="admin",
            is_active=True,
        )
        self.db.add(self.owner)
        self.db.flush()

        self.company = Company(
            name="Acme",
            slug="acme-candidate-auth",
            owner_id=self.owner.id,
            is_active=True,
        )
        self.db.add(self.company)
        self.db.flush()
        self.owner.company_id = self.company.id
        self.db.add(self.owner)

        self.recruiter = User(
            full_name="Recruiter",
            email="recruiter@acme.test",
            hashed_password=hash_password("RecruiterPass1!"),
            role="recruiter",
            company_id=self.company.id,
            is_active=True,
        )
        self.db.add(self.recruiter)
        self.db.flush()

        self.member = CompanyMember(
            company_id=self.company.id,
            user_id=self.recruiter.id,
            role="recruiter",
            is_active=True,
        )
        self.db.add(self.member)
        self.db.flush()

        self.job = Job(
            company_id=self.company.id,
            company_member_id=self.member.id,
            created_by_id=self.recruiter.id,
            title="Backend Engineer",
            status="open",
            is_active=True,
            openings=1,
        )
        self.db.add(self.job)
        self.db.flush()

        self.candidate = Candidate(
            first_name="Ada",
            last_name="Lovelace",
            full_name="Ada Lovelace",
            email="ada@example.com",
            status="new",
            is_active=True,
            hashed_password=hash_password("CandidatePass1!"),
        )
        self.other_candidate = Candidate(
            first_name="Other",
            last_name="Cand",
            full_name="Other Cand",
            email="other@example.com",
            status="new",
            is_active=True,
            hashed_password=hash_password("OtherPass1!"),
        )
        self.inactive_candidate = Candidate(
            first_name="Inactive",
            last_name="Cand",
            full_name="Inactive Cand",
            email="inactive@example.com",
            status="new",
            is_active=False,
            hashed_password=hash_password("InactivePass1!"),
        )
        self.unactivated_candidate = Candidate(
            first_name="Pending",
            last_name="Apply",
            full_name="Pending Apply",
            email="pending.apply@example.com",
            status="new",
            is_active=True,
            hashed_password=None,
        )
        self.db.add_all(
            [
                self.candidate,
                self.other_candidate,
                self.inactive_candidate,
                self.unactivated_candidate,
            ]
        )
        self.db.commit()


@pytest.fixture
def world(auth_db: Session) -> CandidateAuthWorld:
    return CandidateAuthWorld(auth_db)


@pytest.fixture
def client(world: CandidateAuthWorld) -> TestClient:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_candidate_register_and_login_success(client: TestClient) -> None:
    register = client.post(
        "/auth/candidate/register",
        json={
            "full_name": "New Candidate",
            "email": "new.candidate@example.com",
            "password": "SecurePass1!",
        },
    )
    assert register.status_code == 201, register.text
    payload = register.json()
    assert payload["principal"] == PRINCIPAL_CANDIDATE
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    claims = verify_access_token(payload["access_token"])
    assert claims["principal"] == PRINCIPAL_CANDIDATE
    assert claims["sub"]

    login = client.post(
        "/auth/candidate/login",
        json={"email": "new.candidate@example.com", "password": "SecurePass1!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["principal"] == PRINCIPAL_CANDIDATE


def test_candidate_login_invalid_credentials(client: TestClient, world: CandidateAuthWorld) -> None:
    response = client.post(
        "/auth/candidate/login",
        json={"email": world.candidate.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_inactive_candidate_cannot_login_or_access_me(
    client: TestClient,
    world: CandidateAuthWorld,
) -> None:
    login = client.post(
        "/auth/candidate/login",
        json={"email": world.inactive_candidate.email, "password": "InactivePass1!"},
    )
    assert login.status_code == 401

    # Even a previously issued token must fail once the account is inactive.
    token = create_access_token(world.inactive_candidate.id, principal=PRINCIPAL_CANDIDATE)
    me = client.get("/auth/candidate/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401


def test_candidate_me_uses_token_identity_only(client: TestClient, world: CandidateAuthWorld) -> None:
    login = client.post(
        "/auth/candidate/login",
        json={"email": world.candidate.email, "password": "CandidatePass1!"},
    )
    token = login.json()["access_token"]
    me = client.get("/auth/candidate/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["id"] == str(world.candidate.id)
    assert body["email"] == world.candidate.email
    assert body["account_activated"] is True


def test_candidate_cannot_access_other_candidate_resource(
    world: CandidateAuthWorld,
) -> None:
    with pytest.raises(LookupError):
        require_candidate_self(world.candidate, world.other_candidate.id)

    require_candidate_self(world.candidate, world.candidate.id)


def test_candidate_token_rejected_by_recruiter_dependencies(
    client: TestClient,
    world: CandidateAuthWorld,
) -> None:
    login = client.post(
        "/auth/candidate/login",
        json={"email": world.candidate.email, "password": "CandidatePass1!"},
    )
    token = login.json()["access_token"]

    # Staff-only offer list requires get_current_user (principal=user).
    response = client.get(
        f"/offers/candidate/{world.candidate.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_user_token_rejected_by_candidate_me(client: TestClient, world: CandidateAuthWorld) -> None:
    user_token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
    response = client.get(
        "/auth/candidate/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 401


def test_candidate_token_cannot_refresh_via_user_refresh(
    client: TestClient,
    world: CandidateAuthWorld,
) -> None:
    token = create_access_token(world.candidate.id, principal=PRINCIPAL_CANDIDATE)
    response = client.post("/auth/refresh", json={"refresh_token": token})
    assert response.status_code == 401


def test_activate_existing_public_apply_candidate(
    client: TestClient,
    world: CandidateAuthWorld,
) -> None:
    register = client.post(
        "/auth/candidate/register",
        json={
            "full_name": "Pending Apply",
            "email": world.unactivated_candidate.email,
            "password": "ActivatePass1!",
        },
    )
    assert register.status_code == 201, register.text
    assert register.json()["principal"] == PRINCIPAL_CANDIDATE

    world.db.refresh(world.unactivated_candidate)
    assert world.unactivated_candidate.hashed_password is not None
    assert world.unactivated_candidate.id  # same identity reused


def test_duplicate_activated_register_conflicts(client: TestClient, world: CandidateAuthWorld) -> None:
    response = client.post(
        "/auth/candidate/register",
        json={
            "full_name": "Ada Lovelace",
            "email": world.candidate.email,
            "password": "AnotherPass1!",
        },
    )
    assert response.status_code == 409


def test_public_apply_still_creates_and_reuses_candidates(
    world: CandidateAuthWorld,
) -> None:
    class _FakeUpload:
        filename = "resume.pdf"
        content_type = "application/pdf"

        def __init__(self) -> None:
            self.file = BytesIO(b"%PDF-1.4 fake")

        async def read(self, size: int = -1) -> bytes:
            return self.file.read(size)

        def seek(self, offset: int) -> None:
            self.file.seek(offset)

    class _FakeResumeManager:
        def upload_resume(self, _file) -> dict[str, str]:
            return {"path": f"resumes/{uuid4()}.pdf"}

        def delete_resume(self, _path: str) -> None:
            return None

    service = PublicApplyService(
        world.db,
        JobRepository(world.db),
        CandidateRepository(world.db),
        ApplicationRepository(world.db),
        _FakeResumeManager(),
    )

    form = PublicApplyForm(
        email="reuse.me@example.com",
        full_name="Reuse Me",
        phone="555-0100",
    )
    first = service.submit_application(world.job.id, form, _FakeUpload())
    second_form = PublicApplyForm(
        email="Reuse.Me@example.com",
        full_name="Reuse Me Updated",
        phone="555-0101",
    )

    # Different job required to avoid duplicate application constraint.
    other_job = Job(
        company_id=world.company.id,
        company_member_id=world.member.id,
        created_by_id=world.recruiter.id,
        title="Frontend Engineer",
        status="open",
        is_active=True,
        openings=1,
    )
    world.db.add(other_job)
    world.db.commit()

    second = service.submit_application(other_job.id, second_form, _FakeUpload())
    assert first.candidate_id == second.candidate_id

    candidate = CandidateRepository(world.db).get_by_id(first.candidate_id)
    assert candidate is not None
    assert candidate.hashed_password is None
    assert candidate.email == "reuse.me@example.com"

    # Same job again must still conflict.
    with pytest.raises(Exception):
        service.submit_application(world.job.id, form, _FakeUpload())


def test_legacy_user_token_without_principal_claim_still_resolves_as_user(
    client: TestClient,
    world: CandidateAuthWorld,
) -> None:
    # Manually craft a legacy-shaped token (no principal) via jwt.encode path used before.
    import jwt
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings

    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    legacy = jwt.encode(
        {
            "sub": str(world.recruiter.id),
            "exp": expire,
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    payload = verify_access_token(legacy)
    assert payload["principal"] == PRINCIPAL_USER
