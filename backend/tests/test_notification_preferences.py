"""Notification preferences — staff/candidate ownership and delivery gating."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

import app.models  # noqa: F401
from app.core.durable_job import DurableJobType
from app.core.interview_type import InterviewType
from app.core.notification import (
    NotificationCategory,
    NotificationEventType,
    NotificationRecipientType,
)
from app.models.durable_job import DurableJob
from app.models.notification import Notification
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.notification import NotificationRepository
from app.repositories.notification_preference import NotificationPreferenceRepository
from app.schemas.interview import InterviewCreate
from app.schemas.notification import NotificationCreate
from app.schemas.notification_preference import (
    NotificationPreferenceUpdate,
)
from app.services.email_delivery import EmailDeliveryService
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService
from app.services.notification_email import NotificationEmailOrchestrator
from app.services.notification_factory import build_notification_event_producer
from app.services.notification_preference import NotificationPreferenceService
from app.repositories.application import ApplicationRepository
from app.repositories.durable_job import DurableJobRepository
from app.repositories.interview import InterviewRepository
from app.services.durable_job_service import DurableJobService
from app.services.job_handlers import register_default_job_handlers
from tests.offer_test_support import OfferWorld
from tests.test_email_delivery_foundation import RecordingEmailProvider

pytest_plugins = ["tests.offer_test_support"]


def _pref_service(world: OfferWorld) -> NotificationPreferenceService:
    return NotificationPreferenceService(
        NotificationPreferenceRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _notification_service(world: OfferWorld) -> NotificationService:
    prefs = _pref_service(world)
    return NotificationService(
        NotificationRepository(world.db),
        CompanyMemberRepository(world.db),
        preference_service=prefs,
    )


def test_staff_can_read_and_update_own_preferences(world: OfferWorld) -> None:
    service = _pref_service(world)
    defaults = service.get_for_user(world.recruiter)
    assert defaults.email_enabled is True
    assert defaults.in_app_enabled is True
    assert defaults.email_disabled_categories == []

    updated = service.update_for_user(
        world.recruiter,
        NotificationPreferenceUpdate(
            email_enabled=False,
            email_disabled_categories=["offer"],
        ),
    )
    assert updated.email_enabled is False
    assert updated.email_disabled_categories == ["offer"]

    again = service.get_for_user(world.recruiter)
    assert again.email_enabled is False
    assert again.email_disabled_categories == ["offer"]


def test_candidate_can_read_and_update_own_preferences(world: OfferWorld) -> None:
    service = _pref_service(world)
    defaults = service.get_for_candidate(world.candidate)
    assert defaults.email_enabled is True

    updated = service.update_for_candidate(
        world.candidate,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    assert updated.email_enabled is False
    assert service.get_for_candidate(world.candidate).email_enabled is False


def test_cross_recipient_and_company_access_blocked(world: OfferWorld) -> None:
    service = _pref_service(world)
    service.update_for_user(
        world.recruiter,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    # Other company user cannot read recruiter prefs via staff API identity.
    other = service.get_for_user(world.other_recruiter)
    assert other.email_enabled is True  # defaults for other tenant

    staff_row = world.db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.recipient_id == world.recruiter.id
        )
    )
    assert staff_row is not None
    assert staff_row.company_id == world.company.id
    assert staff_row.company_id != world.other_company.id


def test_client_supplied_identity_cannot_bypass_ownership(world: OfferWorld) -> None:
    """Preference APIs derive identity from auth principal — no recipient_id in body."""
    service = _pref_service(world)
    payload = NotificationPreferenceUpdate(email_enabled=False)
    # Updating as recruiter only mutates recruiter row.
    service.update_for_user(world.recruiter, payload)
    candidate_prefs = service.get_for_candidate(world.candidate)
    assert candidate_prefs.email_enabled is True
    hm_prefs = service.get_for_user(world.hiring_manager)
    assert hm_prefs.email_enabled is True


def test_disabling_email_prevents_email_jobs_but_persists_notification(
    world: OfferWorld,
) -> None:
    prefs = _pref_service(world)
    prefs.update_for_candidate(
        world.candidate,
        NotificationPreferenceUpdate(email_enabled=False),
    )

    provider = RecordingEmailProvider()
    jobs = DurableJobService(DurableJobRepository(world.db))
    register_default_job_handlers(jobs, world.db, email_delivery=EmailDeliveryService(provider))
    producer = build_notification_event_producer(
        world.db,
        email_delivery=EmailDeliveryService(provider),
    )
    # Rebuild producer with preference-aware orchestrator sharing this db.
    from app.services.notification_email import NotificationEmailOrchestrator
    from app.services.notification_events import NotificationEventProducer

    producer = NotificationEventProducer(
        _notification_service(world),
        CompanyMemberRepository(world.db),
        email_orchestrator=NotificationEmailOrchestrator(
            email_delivery=EmailDeliveryService(provider),
            job_service=jobs,
            preference_service=prefs,
        ),
    )

    interview_service = InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
    )
    interview_service.notification_events = producer

    start = datetime.now(timezone.utc) + timedelta(days=1)
    interview_service.create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.recruiter_member.id,
            interview_type=InterviewType.PHONE,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            timezone="UTC",
        ),
    )

    notes = list(
        world.db.scalars(
            select(Notification).where(
                Notification.recipient_type == NotificationRecipientType.CANDIDATE.value,
                Notification.recipient_id == world.candidate.id,
            )
        ).all()
    )
    assert len(notes) >= 1

    email_jobs = [
        j
        for j in world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.EMAIL_DELIVERY.value)
        ).all()
        if (j.payload_json or {}).get("notification_id")
        in {str(n.id) for n in notes}
    ]
    assert email_jobs == []


def test_reenable_email_restores_future_delivery(world: OfferWorld) -> None:
    prefs = _pref_service(world)
    prefs.update_for_candidate(
        world.candidate,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    prefs.update_for_candidate(
        world.candidate,
        NotificationPreferenceUpdate(email_enabled=True),
    )

    provider = RecordingEmailProvider()
    jobs = DurableJobService(DurableJobRepository(world.db))
    register_default_job_handlers(jobs, world.db, email_delivery=EmailDeliveryService(provider))
    from app.services.notification_email import NotificationEmailOrchestrator
    from app.services.notification_events import NotificationEventProducer

    producer = NotificationEventProducer(
        _notification_service(world),
        CompanyMemberRepository(world.db),
        email_orchestrator=NotificationEmailOrchestrator(
            email_delivery=EmailDeliveryService(provider),
            job_service=jobs,
            preference_service=prefs,
        ),
    )
    interview_service = InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        CompanyMemberRepository(world.db),
    )
    interview_service.notification_events = producer
    start = datetime.now(timezone.utc) + timedelta(days=2)
    interview_service.create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.recruiter_member.id,
            interview_type=InterviewType.TECHNICAL,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            timezone="UTC",
        ),
    )
    email_jobs = list(
        world.db.scalars(
            select(DurableJob).where(DurableJob.job_type == DurableJobType.EMAIL_DELIVERY.value)
        ).all()
    )
    assert len(email_jobs) >= 1


def test_in_app_preference_hides_from_list_but_persists(world: OfferWorld) -> None:
    prefs = _pref_service(world)
    notif = _notification_service(world)
    created = notif.create_notification(
        NotificationCreate(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=world.recruiter.id,
            company_id=world.company.id,
            category=NotificationCategory.OFFER,
            title="Offer update",
            message="Offer created",
            metadata={"event_type": NotificationEventType.OFFER_CREATED.value},
        )
    )
    prefs.update_for_user(
        world.recruiter,
        NotificationPreferenceUpdate(in_app_disabled_categories=["offer"]),
    )
    listed = notif.list_for_user(world.recruiter)
    assert all(item.id != created.id for item in listed.items)
    # Direct get still works — preference gates surfacing, not ownership.
    fetched = notif.get_for_user(world.recruiter, created.id)
    assert fetched.id == created.id


def test_mandatory_system_category_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(email_disabled_categories=["system"])
    with pytest.raises(ValidationError):
        NotificationPreferenceUpdate(in_app_disabled_categories=["system"])


def test_mandatory_system_still_allowed_when_email_globally_disabled(
    world: OfferWorld,
) -> None:
    prefs = _pref_service(world)
    prefs.update_for_user(
        world.recruiter,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    assert (
        prefs.is_email_allowed(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=world.recruiter.id,
            company_id=world.company.id,
            category=NotificationCategory.SYSTEM,
        )
        is True
    )
    assert (
        prefs.is_email_allowed(
            recipient_type=NotificationRecipientType.USER,
            recipient_id=world.recruiter.id,
            company_id=world.company.id,
            category=NotificationCategory.OFFER,
        )
        is False
    )


def test_staff_email_preference_does_not_affect_candidate(world: OfferWorld) -> None:
    prefs = _pref_service(world)
    prefs.update_for_user(
        world.recruiter,
        NotificationPreferenceUpdate(email_enabled=False),
    )
    assert (
        prefs.is_email_allowed(
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=world.candidate.id,
            company_id=world.company.id,
            category=NotificationCategory.INTERVIEW,
        )
        is True
    )
