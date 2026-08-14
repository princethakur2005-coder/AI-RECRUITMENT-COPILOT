"""Enterprise PostgreSQL audit log foundation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.application_status import ApplicationStatus
from app.core.audit import AUDIT_ACTOR_CANDIDATE, AUDIT_ACTOR_USER, AuditAction, AuditResourceType
from app.core.auth_principals import PRINCIPAL_CANDIDATE
from app.core.calendar import CalendarProviderType
from app.core.interview_type import InterviewType
from app.core.jwt import create_access_token
from app.core.notification import NotificationEventType
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.candidate import Candidate
from app.models.company_member import CompanyMember
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.audit_event import AuditEventRepository
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.repositories.webhook import WebhookRepository
from app.schemas.calendar import CalendarIntegrationCreate
from app.schemas.interview import InterviewCreate
from app.schemas.webhook import WebhookCreate
from app.services.application import ApplicationService
from app.services.calendar_integration_service import CalendarIntegrationService
from app.services.interview_management import InterviewService
from app.services.webhook_service import WebhookService
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


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
def admin_user(world: OfferWorld) -> User:
    admin = User(
        full_name="Audit Admin",
        email=f"audit-admin-{uuid4().hex[:8]}@acme.test",
        hashed_password="hashed",
        role="company_admin",
        company_id=world.company.id,
        is_active=True,
    )
    world.db.add(admin)
    world.db.flush()
    world.db.add(
        CompanyMember(
            company_id=world.company.id,
            user_id=admin.id,
            role="company_admin",
            is_active=True,
        )
    )
    world.db.commit()
    return admin


def _application_service(world: OfferWorld) -> ApplicationService:
    return ApplicationService(
        ApplicationRepository(world.db),
        JobRepository(world.db),
        CandidateRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _interview_service(world: OfferWorld) -> InterviewService:
    return InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _webhook_service(world: OfferWorld) -> WebhookService:
    return WebhookService(
        WebhookRepository(world.db),
        CompanyRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _calendar_service(world: OfferWorld) -> CalendarIntegrationService:
    return CalendarIntegrationService(
        CalendarIntegrationRepository(world.db),
        CompanyRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _events(world: OfferWorld, company_id=None) -> list[AuditEvent]:
    company_id = company_id or world.company.id
    return list(
        world.db.scalars(
            select(AuditEvent)
            .where(AuditEvent.company_id == company_id)
            .order_by(AuditEvent.created_at.asc())
        ).all()
    )


def test_application_status_change_creates_audit(world: OfferWorld) -> None:
    service = _application_service(world)
    updated = service.update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.OFFERED.value,
    )
    assert updated.status == ApplicationStatus.OFFERED.value
    events = [row for row in _events(world) if row.action == AuditAction.APPLICATION_STATUS_CHANGED.value]
    assert len(events) == 1
    event = events[0]
    assert event.company_id == world.company.id
    assert event.actor_type == AUDIT_ACTOR_USER
    assert event.actor_id == world.recruiter.id
    assert event.resource_type == AuditResourceType.APPLICATION.value
    assert event.resource_id == world.application.id
    assert event.metadata_json["previous_status"] == ApplicationStatus.INTERVIEW.value
    assert event.metadata_json["new_status"] == ApplicationStatus.OFFERED.value
    assert event.metadata_json["candidate_id"] == str(world.candidate.id)


def test_offer_lifecycle_creates_audit(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    events = [row for row in _events(world) if row.resource_type == AuditResourceType.OFFER.value]
    assert any(row.action == "offer_created" and str(row.resource_id) == str(created.id) for row in events)
    created_event = next(row for row in events if row.action == "offer_created")
    assert created_event.actor_type == AUDIT_ACTOR_USER
    assert created_event.actor_id == world.recruiter.id
    assert created_event.company_id == world.company.id
    assert "terms" not in (created_event.metadata_json or {})


def test_interview_mutation_creates_audit(world: OfferWorld) -> None:
    start = datetime.now(timezone.utc) + timedelta(days=1)
    created = _interview_service(world).create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.recruiter_member.id,
            interview_type=InterviewType.TECHNICAL,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            timezone="UTC",
            notes="INTERNAL notes must not be audited",
        ),
    )
    events = [row for row in _events(world) if row.action == AuditAction.INTERVIEW_CREATED.value]
    assert len(events) == 1
    event = events[0]
    assert event.resource_id == created.id
    assert event.actor_id == world.recruiter.id
    assert "INTERNAL" not in str(event.metadata_json)
    assert "notes" not in event.metadata_json


def test_webhook_and_calendar_mutations_create_audit(
    world: OfferWorld,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "WEBHOOK_SKIP_DNS_VALIDATION", True)
    monkeypatch.setattr(settings, "WEBHOOK_VALIDATE_DNS", False)
    monkeypatch.setattr(settings, "DEBUG", True)

    webhook = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/audit",
            event_types=[NotificationEventType.OFFER_CREATED.value],
        ),
    )
    calendar = _calendar_service(world).create(
        admin_user,
        world.company.id,
        CalendarIntegrationCreate(
            provider_type=CalendarProviderType.FAKE,
            display_name="Audit Calendar",
            credentials={"refresh_token": "super-secret-token", "client_secret": "hidden"},
        ),
    )
    events = _events(world)
    webhook_event = next(row for row in events if row.action == AuditAction.WEBHOOK_CREATED.value)
    calendar_event = next(row for row in events if row.action == AuditAction.CALENDAR_INTEGRATION_CREATED.value)
    assert webhook_event.resource_id == webhook.id
    assert calendar_event.resource_id == calendar.id
    blob = str(webhook_event.metadata_json) + str(calendar_event.metadata_json)
    assert webhook.signing_secret not in blob
    assert "super-secret-token" not in blob
    assert "hidden" not in blob
    assert "credentials" not in calendar_event.metadata_json
    assert calendar_event.metadata_json["credentials_configured"] is True


def test_cross_company_audit_isolation(world: OfferWorld) -> None:
    _application_service(world).update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.OFFERED.value,
    )
    _application_service(world).update_application_status(
        world.other_recruiter,
        world.other_application.id,
        ApplicationStatus.OFFERED.value,
    )
    own = _events(world, world.company.id)
    other = _events(world, world.other_company.id)
    assert all(row.company_id == world.company.id for row in own)
    assert all(row.company_id == world.other_company.id for row in other)
    assert {row.resource_id for row in own} != {row.resource_id for row in other}


def test_candidate_and_staff_actor_separation(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    world.offer_service.submit_for_approval(world.recruiter, created.id)
    world.offer_service.approve_offer(world.hiring_manager, created.id)
    world.offer_service.accept_offer(world.candidate, created.id)
    events = [row for row in _events(world) if row.resource_type == AuditResourceType.OFFER.value]
    staff = next(row for row in events if row.action == "offer_created")
    candidate = next(row for row in events if row.action == "offer_accepted")
    assert staff.actor_type == AUDIT_ACTOR_USER
    assert staff.actor_id == world.recruiter.id
    assert candidate.actor_type == AUDIT_ACTOR_CANDIDATE
    assert candidate.actor_id == world.candidate.id
    application_audits = [
        row for row in _events(world) if row.action == AuditAction.APPLICATION_STATUS_CHANGED.value
    ]
    assert application_audits == []


def test_audit_records_cannot_be_updated_or_deleted_via_api(api_client, world: OfferWorld) -> None:
    _application_service(world).update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.OFFERED.value,
    )
    client = api_client(world.recruiter)
    listed = client.get("/audit-logs")
    assert listed.status_code == 200, listed.text
    event_id = listed.json()["items"][0]["id"]
    assert client.post("/audit-logs", json={"action": "forged"}).status_code in {404, 405, 422}
    assert client.patch(f"/audit-logs/{event_id}", json={"action": "tamper"}).status_code in {404, 405}
    assert client.delete(f"/audit-logs/{event_id}").status_code in {404, 405}
    with pytest.raises(PermissionError, match="append-only"):
        AuditEventRepository(world.db).update(_events(world)[0], {"action": "tamper"})
    with pytest.raises(PermissionError, match="append-only"):
        AuditEventRepository(world.db).delete(_events(world)[0])


def test_sensitive_credentials_are_not_persisted(
    world: OfferWorld,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.core.audit import sanitize_audit_metadata

    settings = get_settings()
    monkeypatch.setattr(settings, "WEBHOOK_SKIP_DNS_VALIDATION", True)
    monkeypatch.setattr(settings, "WEBHOOK_VALIDATE_DNS", False)
    monkeypatch.setattr(settings, "DEBUG", True)
    created = _webhook_service(world).create(
        admin_user,
        world.company.id,
        WebhookCreate(
            url="https://hooks.example.com/secret",
            event_types=[NotificationEventType.OFFER_CREATED.value],
            metadata={"signing_secret": "should-not-land", "note": "ok"},
        ),
    )
    event = next(row for row in _events(world) if row.action == AuditAction.WEBHOOK_CREATED.value)
    assert "signing_secret" not in event.metadata_json
    assert created.signing_secret not in str(event.metadata_json)
    cleaned = sanitize_audit_metadata(
        {"password": "x", "jwt": "y", "credentials": {"token": "z"}, "action": "keep"}
    )
    assert cleaned == {"action": "keep"}


def test_failed_domain_operation_does_not_audit(world: OfferWorld) -> None:
    before = len(_events(world))
    with pytest.raises(ValueError):
        _application_service(world).update_application_status(
            world.recruiter,
            world.application.id,
            ApplicationStatus.APPLIED.value,
        )
    assert len(_events(world)) == before
    start = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(ValueError):
        _interview_service(world).create_interview(
            world.recruiter,
            InterviewCreate(
                application_id=world.application.id,
                interviewer_member_id=world.recruiter_member.id,
                interview_type=InterviewType.TECHNICAL,
                scheduled_start=start,
                scheduled_end=start,
                timezone="UTC",
            ),
        )
    assert len(_events(world)) == before


def test_candidate_cannot_read_staff_audit_api(candidate_api_client, world: OfferWorld) -> None:
    response = candidate_api_client(world.candidate).get("/audit-logs")
    assert response.status_code == 401


def test_interviewer_cannot_read_audit_logs(api_client, world: OfferWorld) -> None:
    assert api_client(world.viewer).get("/audit-logs").status_code == 403


def test_other_company_cannot_see_audit_via_api(api_client, world: OfferWorld) -> None:
    _application_service(world).update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.OFFERED.value,
    )
    payload = api_client(world.other_recruiter).get("/audit-logs").json()
    assert payload["total"] == 0 or all(
        item["company_id"] == str(world.other_company.id) for item in payload["items"]
    )
    assert all(item["resource_id"] != str(world.application.id) for item in payload["items"])
