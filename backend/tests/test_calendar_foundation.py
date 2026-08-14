"""Calendar integration foundation — provider-neutral sync via durable jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

import app.models  # noqa: F401
from app.core.calendar import (
    CalendarProviderType,
    CalendarSyncOperation,
    CalendarSyncStatus,
)
from app.core.durable_job import DurableJobStatus, DurableJobType
from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType
from app.models.durable_job import DurableJob
from app.models.interview_calendar_sync import InterviewCalendarSync
from app.models.user import User
from app.repositories.application import ApplicationRepository
from app.repositories.calendar_integration import CalendarIntegrationRepository
from app.repositories.company import CompanyRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.durable_job import DurableJobRepository
from app.repositories.interview import InterviewRepository
from app.repositories.interview_calendar_sync import InterviewCalendarSyncRepository
from app.schemas.calendar import (
    CalendarEventRequest,
    CalendarIntegrationCreate,
    CalendarProviderError,
)
from app.schemas.interview import InterviewCreate, InterviewUpdate
from app.services.calendar_integration_service import CalendarIntegrationService
from app.services.calendar_provider import FakeCalendarProvider, build_calendar_provider
from app.services.calendar_sync import CalendarSyncService
from app.services.durable_job_service import DurableJobService
from app.services.durable_job_worker import DurableJobWorker
from app.services.interview_management import InterviewService
from app.services.job_handlers import register_default_job_handlers
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


@pytest.fixture
def admin_user(world: OfferWorld) -> User:
    admin = User(
        full_name="Calendar Admin",
        email=f"cal-admin-{uuid4().hex[:8]}@acme.test",
        hashed_password="hashed",
        role="company_admin",
        company_id=world.company.id,
        is_active=True,
    )
    world.db.add(admin)
    world.db.flush()
    from app.models.company_member import CompanyMember

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


def _fake_and_jobs(world: OfferWorld) -> tuple[FakeCalendarProvider, DurableJobService, CalendarSyncService]:
    fake = FakeCalendarProvider()
    jobs = DurableJobService(DurableJobRepository(world.db))
    register_default_job_handlers(jobs, world.db, fake_calendar_provider=fake)
    sync = CalendarSyncService(
        InterviewCalendarSyncRepository(world.db),
        CalendarIntegrationRepository(world.db),
        InterviewRepository(world.db),
        job_service=jobs,
    )
    return fake, jobs, sync


def _interview_service(world: OfferWorld, sync: CalendarSyncService) -> InterviewService:
    return InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
        calendar_sync_service=sync,
    )


def _connect_fake(world: OfferWorld, admin: User, *, credentials: dict | None = None):
    service = CalendarIntegrationService(
        CalendarIntegrationRepository(world.db),
        CompanyRepository(world.db),
        CompanyMemberRepository(world.db),
    )
    return service.create(
        admin,
        world.company.id,
        CalendarIntegrationCreate(
            provider_type=CalendarProviderType.FAKE,
            display_name="Test Calendar",
            credentials=credentials or {"access_token": "tok_secret_value"},
        ),
    )


def _schedule_payload(world: OfferWorld) -> InterviewCreate:
    start = datetime.now(timezone.utc) + timedelta(days=1)
    return InterviewCreate(
        application_id=world.application.id,
        interviewer_member_id=world.recruiter_member.id,
        interview_type=InterviewType.TECHNICAL,
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=1),
        timezone="UTC",
        meeting_link="https://meet.example.com/abc",
        location=None,
        notes="Internal recruiter notes — must not leave ATS",
    )


def test_calendar_provider_abstraction_can_create_event() -> None:
    provider = build_calendar_provider(CalendarProviderType.FAKE)
    assert isinstance(provider, FakeCalendarProvider)
    result = provider.create_event(
        CalendarEventRequest(
            interview_id=uuid4(),
            company_id=uuid4(),
            title="Interview — Backend",
            start_at=datetime.now(timezone.utc),
            end_at=datetime.now(timezone.utc) + timedelta(hours=1),
            timezone="UTC",
        )
    )
    assert result.external_event_id
    assert result.provider_type == CalendarProviderType.FAKE


def test_interview_scheduling_creates_calendar_sync_job(
    world: OfferWorld, admin_user: User
) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)

    created = service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])

    sync_row = world.db.scalar(
        select(InterviewCalendarSync).where(InterviewCalendarSync.interview_id == created.id)
    )
    assert sync_row is not None
    assert sync_row.sync_status == CalendarSyncStatus.SYNCED.value
    assert sync_row.external_event_id
    assert len(fake.created) == 1

    job_rows = list(
        world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
        ).all()
    )
    assert len(job_rows) >= 1
    assert job_rows[0].status == DurableJobStatus.SUCCEEDED.value


def test_interview_update_creates_update_sync_job(world: OfferWorld, admin_user: User) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    created = service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])
    fake.created.clear()

    new_start = datetime.now(timezone.utc) + timedelta(days=2)
    service.update_interview(
        world.recruiter,
        created.id,
        InterviewUpdate(
            scheduled_start=new_start,
            scheduled_end=new_start + timedelta(hours=1),
        ),
    )
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])
    assert len(fake.updated) == 1


def test_interview_cancellation_creates_cancel_sync_job(
    world: OfferWorld, admin_user: User
) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    created = service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])

    service.update_interview(
        world.recruiter,
        created.id,
        InterviewUpdate(status=InterviewStatus.CANCELLED),
    )
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])
    assert len(fake.cancelled) == 1
    sync_row = world.db.scalar(
        select(InterviewCalendarSync).where(InterviewCalendarSync.interview_id == created.id)
    )
    assert sync_row is not None
    assert sync_row.sync_status == CalendarSyncStatus.CANCELLED.value


def test_provider_failure_does_not_rollback_interview(
    world: OfferWorld, admin_user: User
) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    fake.fail_next = CalendarProviderError("provider down", retryable=True, error_code="down")
    service = _interview_service(world, sync)

    created = service.create_interview(world.recruiter, _schedule_payload(world))
    assert created.status == InterviewStatus.SCHEDULED
    # Interview persisted even before/without successful calendar sync.
    row = InterviewRepository(world.db).get_by_id_for_company(created.id, world.company.id)
    assert row is not None
    assert row.status == InterviewStatus.SCHEDULED.value

    DurableJobWorker(jobs, worker_id="w1").process_one(job_types=[DurableJobType.CALENDAR_SYNC.value])
    job = world.db.scalar(
        select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
    )
    assert job is not None
    assert job.status == DurableJobStatus.FAILED_RETRYABLE.value
    row2 = InterviewRepository(world.db).get_by_id_for_company(created.id, world.company.id)
    assert row2 is not None
    assert row2.status == InterviewStatus.SCHEDULED.value


def test_reuses_existing_durable_job_infrastructure(
    world: OfferWorld, admin_user: User
) -> None:
    _, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    service.create_interview(world.recruiter, _schedule_payload(world))
    job = world.db.scalar(
        select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
    )
    assert job is not None
    assert job.job_type == DurableJobType.CALENDAR_SYNC.value
    # Same DurableJobService / worker path as email/webhook.
    assert isinstance(jobs, DurableJobService)


def test_duplicate_sync_submission_idempotent(world: OfferWorld, admin_user: User) -> None:
    _, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    created = service.create_interview(world.recruiter, _schedule_payload(world))
    interview = InterviewRepository(world.db).get_by_id_for_company(created.id, world.company.id)
    assert interview is not None
    sync.on_interview_scheduled(interview)
    sync.on_interview_scheduled(interview)
    create_jobs = [
        j
        for j in world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
        ).all()
        if (j.payload_json or {}).get("operation") == CalendarSyncOperation.CREATE.value
        and (j.payload_json or {}).get("interview_id") == str(created.id)
    ]
    assert len({j.idempotency_key for j in create_jobs}) == 1
    assert len(create_jobs) == 1


def test_external_event_id_persisted_safely(world: OfferWorld, admin_user: User) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    created = service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])
    sync_row = world.db.scalar(
        select(InterviewCalendarSync).where(InterviewCalendarSync.interview_id == created.id)
    )
    assert sync_row is not None
    first_id = sync_row.external_event_id
    assert first_id
    assert first_id == fake.created[0].external_event_id

    # Persist path must not silently replace an existing external id with another.
    from app.services.job_handlers.calendar_sync import CalendarSyncJobHandler

    handler = CalendarSyncJobHandler(world.db, fake_provider=fake)
    handler._persist_success(
        sync_id=sync_row.id,
        interview_id=created.id,
        company_id=world.company.id,
        integration_id=sync_row.calendar_integration_id,
        operation=CalendarSyncOperation.CREATE,
        external_event_id="different-external-id",
        existing_external_event_id=first_id,
    )
    world.db.commit()
    world.db.refresh(sync_row)
    assert sync_row.external_event_id == first_id


def test_retryable_provider_failures_follow_durable_job_retry(
    world: OfferWorld, admin_user: User
) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    fake.fail_next = CalendarProviderError("temp", retryable=True, error_code="temp")
    service = _interview_service(world, sync)
    service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_one(job_types=[DurableJobType.CALENDAR_SYNC.value])
    job = world.db.scalar(
        select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
    )
    assert job is not None
    assert job.status == DurableJobStatus.FAILED_RETRYABLE.value
    assert job.next_run_at is not None


def test_tenant_isolation_preserved(world: OfferWorld, admin_user: User) -> None:
    service = CalendarIntegrationService(
        CalendarIntegrationRepository(world.db),
        CompanyRepository(world.db),
        CompanyMemberRepository(world.db),
    )
    created = _connect_fake(world, admin_user)
    with pytest.raises(PermissionError):
        service.get(world.other_recruiter, world.company.id, created.id)
    with pytest.raises(LookupError):
        service.get(world.other_recruiter, world.other_company.id, created.id)


def test_credentials_never_returned_by_api(world: OfferWorld, admin_user: User) -> None:
    created = _connect_fake(
        world,
        admin_user,
        credentials={"refresh_token": "super-secret-refresh", "access_token": "atk"},
    )
    dumped = created.model_dump()
    assert "credentials" not in dumped
    assert "credentials_sealed" not in dumped
    assert dumped["has_credentials"] is True
    blob = str(dumped)
    assert "super-secret-refresh" not in blob
    assert "atk" not in blob


def test_credentials_never_in_job_payload(world: OfferWorld, admin_user: User) -> None:
    _, jobs, sync = _fake_and_jobs(world)
    _connect_fake(
        world,
        admin_user,
        credentials={"access_token": "never-in-payload"},
    )
    service = _interview_service(world, sync)
    service.create_interview(world.recruiter, _schedule_payload(world))
    job = world.db.scalar(
        select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
    )
    assert job is not None
    blob = str(job.payload_json)
    assert "never-in-payload" not in blob
    assert "credentials" not in blob.lower()
    assert "access_token" not in blob.lower()


def test_not_connected_without_integration(world: OfferWorld) -> None:
    _, _, sync = _fake_and_jobs(world)
    service = _interview_service(world, sync)
    created = service.create_interview(world.recruiter, _schedule_payload(world))
    sync_row = world.db.scalar(
        select(InterviewCalendarSync).where(InterviewCalendarSync.interview_id == created.id)
    )
    assert sync_row is not None
    assert sync_row.sync_status == CalendarSyncStatus.NOT_CONNECTED.value
    jobs = list(
        world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.CALENDAR_SYNC.value)
        ).all()
    )
    assert jobs == []


def test_notes_not_sent_to_calendar_provider(world: OfferWorld, admin_user: User) -> None:
    fake, jobs, sync = _fake_and_jobs(world)
    _connect_fake(world, admin_user)
    service = _interview_service(world, sync)
    service.create_interview(world.recruiter, _schedule_payload(world))
    DurableJobWorker(jobs, worker_id="w1").process_batch(job_types=[DurableJobType.CALENDAR_SYNC.value])
    assert fake.created
    assert "Internal recruiter notes" not in (fake.created[0].description or "")
