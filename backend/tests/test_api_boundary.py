"""Production API boundary hardening regression tests."""

from __future__ import annotations

from collections.abc import Callable
from json import dumps

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.jwt import create_access_token
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.candidate import Candidate
from app.models.user import User
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]

_LEGACY_DASHBOARD_PATHS = (
    "/dashboard/summary",
    "/dashboard/pipeline-metrics",
    "/dashboard/funnel",
    "/dashboard/job-metrics",
    "/dashboard/interviews",
    "/dashboard/activities",
    "/dashboard/ai-activities",
)
_FORBIDDEN_RESPONSE_SUBSTRINGS = (
    "hashed_password",
    "signing_secret",
    "smtp_password",
    "credentials_sealed",
    "webhook_secret",
)


@pytest.fixture
def api_client(world: OfferWorld) -> Callable[[User], TestClient]:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db

    def _as(user: User) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _as
    app.dependency_overrides.clear()


@pytest.fixture
def candidate_api_client(world: OfferWorld) -> Callable[[Candidate], TestClient]:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)

    def _as(candidate: Candidate) -> TestClient:
        token = create_access_token(candidate.id, principal=PRINCIPAL_CANDIDATE)
        client = TestClient(app)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    yield _as
    app.dependency_overrides.clear()


@pytest.mark.parametrize("path", _LEGACY_DASHBOARD_PATHS)
def test_legacy_dashboard_routes_require_authentication(world: OfferWorld, path: str) -> None:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = TestClient(app).get(path)
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", _LEGACY_DASHBOARD_PATHS)
def test_legacy_dashboard_routes_reject_candidate_jwt(
    candidate_api_client,
    world: OfferWorld,
    path: str,
) -> None:
    response = candidate_api_client(world.candidate).get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", _LEGACY_DASHBOARD_PATHS)
def test_legacy_dashboard_routes_allow_staff(api_client, world: OfferWorld, path: str) -> None:
    response = api_client(world.recruiter).get(path)
    assert response.status_code == 200


def test_legacy_dashboard_routes_forbid_interviewer(api_client, world: OfferWorld) -> None:
    response = api_client(world.viewer).get("/dashboard/summary")
    assert response.status_code == 403


def test_health_dependencies_hidden_outside_debug(monkeypatch) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "DEBUG", False)
    response = TestClient(app).get("/health/dependencies")
    assert response.status_code == 404


def test_health_dependencies_available_in_debug(monkeypatch) -> None:
    import app.core.config as config_module

    monkeypatch.setattr(config_module.settings, "DEBUG", True)
    response = TestClient(app).get("/health/dependencies")
    assert response.status_code == 200
    assert "dependencies" in response.json()


def test_audit_api_strips_sensitive_metadata(api_client, world: OfferWorld) -> None:
    event = AuditEvent(
        company_id=world.company.id,
        actor_type="user",
        actor_id=world.recruiter.id,
        action="webhook.created",
        resource_type="webhook",
        resource_id=world.job.id,
        metadata_json={
            "signing_secret": "whsec_super_secret",
            "smtp_password": "mail-secret",
            "safe_field": "visible",
        },
    )
    world.db.add(event)
    world.db.commit()

    response = api_client(world.recruiter).get("/audit-logs")
    assert response.status_code == 200
    payload = response.json()
    serialized = dumps(payload)
    for forbidden in _FORBIDDEN_RESPONSE_SUBSTRINGS:
        assert forbidden not in serialized
    assert "whsec_super_secret" not in serialized
    assert "mail-secret" not in serialized
    assert payload["items"][0]["metadata"]["safe_field"] == "visible"


def test_search_remains_staff_only(api_client, candidate_api_client, world: OfferWorld) -> None:
    assert candidate_api_client(world.candidate).get("/search", params={"q": "Ada"}).status_code == 401
    assert api_client(world.recruiter).get("/search", params={"q": "Ada"}).status_code == 200


def test_public_apply_remains_unauthenticated(world: OfferWorld, monkeypatch) -> None:
    from datetime import datetime, timezone
    from io import BytesIO

    from app.core.application_status import ApplicationStatus
    from app.services.public_apply import PublicApplyService

    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)

    def _submit(_self, job_id, form, resume):  # noqa: ANN001
        from app.schemas.public_apply import PublicApplyResponse

        return PublicApplyResponse(
            application_id=world.application.id,
            candidate_id=world.candidate.id,
            job_id=job_id,
            status=ApplicationStatus.APPLIED,
            applied_at=datetime.now(timezone.utc),
            message="Application submitted",
        )

    monkeypatch.setattr(PublicApplyService, "submit_application", _submit)
    try:
        client = TestClient(app)
        response = client.post(
            f"/public/jobs/{world.job.id}/apply",
            data={"email": "new@example.com", "full_name": "New Candidate"},
            files={"resume": ("resume.pdf", BytesIO(b"pdf"), "application/pdf")},
        )
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()
