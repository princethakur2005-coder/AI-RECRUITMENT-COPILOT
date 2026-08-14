"""Notification foundation — persistence, recipient isolation, read-state."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth_principals import PRINCIPAL_CANDIDATE, PRINCIPAL_USER
from app.core.jwt import create_access_token
from app.core.notification import (
    NotificationCategory,
    NotificationRecipientType,
    NotificationStatus,
)
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.candidate import Candidate
from app.models.user import User
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.notification import NotificationRepository
from app.schemas.notification import NotificationCreate
from app.services.notification import NotificationService
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]

FRONTEND_NEXT_CONFIG = Path(__file__).resolve().parents[2] / "frontend" / "next.config.ts"
FRONTEND_NOTIFICATIONS_PAGE = (
    Path(__file__).resolve().parents[2] / "frontend" / "pages" / "notifications.tsx"
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


@pytest.fixture
def notification_service(world: OfferWorld) -> NotificationService:
    return NotificationService(
        NotificationRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _staff_notification(
    service: NotificationService,
    *,
    user_id,
    company_id,
    message: str = "Staff notice",
    title: str = "Hello",
):
    return service.create_notification(
        NotificationCreate(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=user_id,
            company_id=company_id,
            title=title,
            message=message,
            category=NotificationCategory.SYSTEM,
            entity_type="offer",
            entity_id=uuid4(),
            metadata={"internal_secret": "must-not-expand-domain"},
        )
    )


def _candidate_notification(
    service: NotificationService,
    *,
    candidate_id,
    company_id=None,
    message: str = "Candidate notice",
):
    return service.create_notification(
        NotificationCreate(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=candidate_id,
            company_id=company_id,
            title="Candidate update",
            message=message,
            category=NotificationCategory.OFFER,
        )
    )


def test_company_user_sees_only_own_notifications(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    mine = _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="Only recruiter",
    )
    _staff_notification(
        notification_service,
        user_id=world.hiring_manager.id,
        company_id=world.company.id,
        message="Only HM",
    )

    response = api_client(world.recruiter).get("/notifications")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(mine.id)
    assert payload["items"][0]["message"] == "Only recruiter"
    assert "internal_secret" in payload["items"][0]["metadata"]


def test_candidate_sees_only_own_notifications(
    world: OfferWorld,
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    mine = _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
    )
    _candidate_notification(
        notification_service,
        candidate_id=world.other_candidate.id,
        company_id=world.other_company.id,
    )

    response = candidate_api_client(world.candidate).get("/candidate/notifications")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == str(mine.id)
    assert payload["items"][0]["recipient_type"] == "candidate"


def test_cross_company_staff_notification_access_blocked(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    foreign = _staff_notification(
        notification_service,
        user_id=world.other_recruiter.id,
        company_id=world.other_company.id,
        message="Other tenant",
    )

    list_response = api_client(world.recruiter).get("/notifications")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0

    get_response = api_client(world.recruiter).get(f"/notifications/{foreign.id}")
    assert get_response.status_code == 404

    summary = api_client(world.recruiter).get("/notifications/summary")
    assert summary.status_code == 200
    assert summary.json()["unread_count"] == 0

    mark_all = api_client(world.recruiter).post("/notifications/read-all")
    assert mark_all.status_code == 200
    assert mark_all.json()["updated_count"] == 0


def test_candidate_cannot_access_staff_notifications(
    world: OfferWorld,
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    staff = _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
    )

    list_response = candidate_api_client(world.candidate).get("/candidate/notifications")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0

    get_response = candidate_api_client(world.candidate).get(f"/candidate/notifications/{staff.id}")
    assert get_response.status_code == 404

    # Candidate JWT must not use staff notification routes.
    staff_route = candidate_api_client(world.candidate).get("/notifications")
    assert staff_route.status_code == 401
    assert candidate_api_client(world.candidate).get("/notifications/summary").status_code == 401
    assert candidate_api_client(world.candidate).post("/notifications/read-all").status_code == 401


def test_staff_cannot_use_candidate_notification_routes(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    candidate_note = _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
    )

    response = api_client(world.recruiter).get("/candidate/notifications")
    assert response.status_code == 401
    assert api_client(world.recruiter).get("/candidate/notifications/summary").status_code == 401
    assert api_client(world.recruiter).post("/candidate/notifications/read-all").status_code == 401

    # Staff listing does not include candidate-recipient rows.
    staff_list = api_client(world.recruiter).get("/notifications")
    assert staff_list.status_code == 200
    assert staff_list.json()["total"] == 0

    staff_get = api_client(world.recruiter).get(f"/notifications/{candidate_note.id}")
    assert staff_get.status_code == 404


def test_unread_read_state_and_idempotent_mark_read(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    note = _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
    )
    assert note.status == NotificationStatus.UNREAD
    assert note.read is False

    client = api_client(world.recruiter)
    first = client.post(f"/notifications/{note.id}/read")
    assert first.status_code == 200
    assert first.json()["status"] == "read"
    assert first.json()["read"] is True
    assert first.json()["read_at"] is not None

    second = client.post(f"/notifications/{note.id}/read")
    assert second.status_code == 200
    assert second.json()["status"] == "read"
    assert second.json()["read_at"] == first.json()["read_at"]

    patch = client.patch(f"/notifications/{note.id}", json={"read": True})
    assert patch.status_code == 200
    assert patch.json()["status"] == "read"


def test_candidate_mark_read_idempotent(
    world: OfferWorld,
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    note = _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
    )
    client = candidate_api_client(world.candidate)
    first = client.post(f"/candidate/notifications/{note.id}/read")
    second = client.post(f"/candidate/notifications/{note.id}/read")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "read"
    assert second.json()["read_at"] == first.json()["read_at"]


def test_notification_retrieval_does_not_leak_unrelated_entity_payload(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    note = _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="Offer ready",
    )
    response = api_client(world.recruiter).get(f"/notifications/{note.id}")
    assert response.status_code == 200
    body = response.json()
    # Related reference is an opaque id/type only — no nested offer/application dump.
    assert body["entity_type"] == "offer"
    assert "entity_id" in body
    assert "application" not in body
    assert "offer" not in body
    assert "candidate" not in body


def test_staff_token_still_required_for_notifications(
    world: OfferWorld,
) -> None:
    def _override_db():
        try:
            yield world.db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    try:
        assert client.get("/notifications").status_code == 401
        token = create_access_token(world.recruiter.id, principal=PRINCIPAL_USER)
        authorized = TestClient(app)
        authorized.headers.update({"Authorization": f"Bearer {token}"})
        assert authorized.get("/notifications").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_staff_unread_summary(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    first = _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="one",
    )
    _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="two",
    )
    notification_service.mark_for_user(world.recruiter, first.id, NotificationStatus.READ)

    response = api_client(world.recruiter).get("/notifications/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["unread_count"] == 1
    assert payload["read_count"] == 1


def test_candidate_unread_summary(
    world: OfferWorld,
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    first = _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="one",
    )
    _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="two",
    )
    notification_service.mark_for_candidate(world.candidate, first.id, NotificationStatus.READ)

    response = candidate_api_client(world.candidate).get("/candidate/notifications/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["unread_count"] == 1
    assert payload["read_count"] == 1


def test_unread_summary_excludes_unrelated_recipients(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    _staff_notification(
        notification_service,
        user_id=world.hiring_manager.id,
        company_id=world.company.id,
        message="hm only",
    )
    _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="candidate only",
    )

    staff_summary = api_client(world.recruiter).get("/notifications/summary")
    assert staff_summary.status_code == 200
    assert staff_summary.json() == {"total": 0, "unread_count": 0, "read_count": 0}

    hm_summary = api_client(world.hiring_manager).get("/notifications/summary")
    assert hm_summary.json()["unread_count"] == 1

    candidate_summary = candidate_api_client(world.candidate).get("/candidate/notifications/summary")
    assert candidate_summary.json()["unread_count"] == 1


def test_staff_mark_all_read_idempotent(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    notification_service: NotificationService,
) -> None:
    _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="a",
    )
    _staff_notification(
        notification_service,
        user_id=world.recruiter.id,
        company_id=world.company.id,
        message="b",
    )
    _staff_notification(
        notification_service,
        user_id=world.hiring_manager.id,
        company_id=world.company.id,
        message="other recipient",
    )

    client = api_client(world.recruiter)
    first = client.post("/notifications/read-all")
    assert first.status_code == 200
    assert first.json()["updated_count"] == 2
    assert first.json()["unread_count"] == 0

    second = client.post("/notifications/read-all")
    assert second.status_code == 200
    assert second.json()["updated_count"] == 0
    assert second.json()["unread_count"] == 0

    # Other recipient remains unread.
    hm_summary = api_client(world.hiring_manager).get("/notifications/summary")
    assert hm_summary.json()["unread_count"] == 1


def test_candidate_mark_all_read_idempotent(
    world: OfferWorld,
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="a",
    )
    _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="b",
    )
    _candidate_notification(
        notification_service,
        candidate_id=world.other_candidate.id,
        company_id=world.other_company.id,
        message="other",
    )

    client = candidate_api_client(world.candidate)
    first = client.post("/candidate/notifications/read-all")
    assert first.status_code == 200
    assert first.json()["updated_count"] == 2
    assert first.json()["unread_count"] == 0

    second = client.post("/candidate/notifications/read-all")
    assert second.status_code == 200
    assert second.json()["updated_count"] == 0
    assert second.json()["unread_count"] == 0

    other_summary = candidate_api_client(world.other_candidate).get("/candidate/notifications/summary")
    assert other_summary.json()["unread_count"] == 1


def test_client_supplied_recipient_identity_cannot_bypass_ownership(
    world: OfferWorld,
    api_client: Callable[[User], TestClient],
    candidate_api_client: Callable[[Candidate], TestClient],
    notification_service: NotificationService,
) -> None:
    hm_note = _staff_notification(
        notification_service,
        user_id=world.hiring_manager.id,
        company_id=world.company.id,
        message="hm",
    )
    candidate_note = _candidate_notification(
        notification_service,
        candidate_id=world.candidate.id,
        company_id=world.company.id,
        message="cand",
    )

    # Query/body recipient hints must be ignored; ownership comes from JWT/principal only.
    staff_client = api_client(world.recruiter)
    assert staff_client.get(f"/notifications/{hm_note.id}?recipient_id={world.hiring_manager.id}").status_code == 404
    assert (
        staff_client.patch(
            f"/notifications/{hm_note.id}",
            json={"read": True, "recipient_id": str(world.hiring_manager.id)},
        ).status_code
        == 404
    )
    assert (
        staff_client.post(
            "/notifications/read-all",
            json={"recipient_id": str(world.hiring_manager.id), "company_id": str(world.company.id)},
        ).json()["updated_count"]
        == 0
    )

    candidate_client = candidate_api_client(world.other_candidate)
    assert (
        candidate_client.get(
            f"/candidate/notifications/{candidate_note.id}?candidate_id={world.candidate.id}"
        ).status_code
        == 404
    )
    assert (
        candidate_client.post(
            "/candidate/notifications/read-all",
            json={"candidate_id": str(world.candidate.id)},
        ).json()["updated_count"]
        == 0
    )


def test_frontend_notification_api_proxy_contract() -> None:
    """Browser page stays on `/notifications`; API calls use `/api/notifications`."""
    next_config = FRONTEND_NEXT_CONFIG.read_text(encoding="utf-8")
    page_source = FRONTEND_NOTIFICATIONS_PAGE.read_text(encoding="utf-8")

    assert 'source: "/api/:path*"' in next_config
    assert 'destination: `${API_BASE_URL}/:path*`' in next_config
    # Ambiguous page/API collision rewrite must not exist.
    assert 'source: "/notifications"' not in next_config
    assert 'source: "/notifications/:path*"' not in next_config

    assert 'const NOTIFICATIONS_ENDPOINT = "/api/notifications"' in page_source
    assert "${NOTIFICATIONS_ENDPOINT}/read-all" in page_source
