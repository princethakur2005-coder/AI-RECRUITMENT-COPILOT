"""Notification event producers — Application / Interview / Offer lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select

from app.core.application_status import ApplicationStatus
from app.core.interview_status import InterviewStatus
from app.core.interview_type import InterviewType
from app.core.notification import (
    NotificationCategory,
    NotificationEventType,
    NotificationRecipientType,
)
from app.core.offer_status import OfferStatus
from app.models.notification import Notification
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.company_member import CompanyMemberRepository
from app.repositories.interview import InterviewRepository
from app.repositories.job import JobRepository
from app.repositories.notification import NotificationRepository
from app.schemas.interview import InterviewCreate, InterviewUpdate
from app.services.application import ApplicationService
from app.services.interview_management import InterviewService
from app.services.notification import NotificationService
from tests.offer_test_support import OfferWorld

pytest_plugins = ["tests.offer_test_support"]


def _notification_service(world: OfferWorld) -> NotificationService:
    return NotificationService(
        NotificationRepository(world.db),
        CompanyMemberRepository(world.db),
    )


def _application_service(world: OfferWorld) -> ApplicationService:
    member_repository = CompanyMemberRepository(world.db)
    return ApplicationService(
        ApplicationRepository(world.db),
        JobRepository(world.db),
        CandidateRepository(world.db),
        member_repository,
        notification_service=_notification_service(world),
    )


def _interview_service(world: OfferWorld) -> InterviewService:
    member_repository = CompanyMemberRepository(world.db)
    return InterviewService(
        InterviewRepository(world.db),
        ApplicationRepository(world.db),
        member_repository,
        notification_service=_notification_service(world),
    )


def _rows_for(
    world: OfferWorld,
    *,
    recipient_type: NotificationRecipientType,
    recipient_id,
    event_type: str | None = None,
) -> list[Notification]:
    statement = select(Notification).where(
        Notification.recipient_type == recipient_type.value,
        Notification.recipient_id == recipient_id,
    )
    rows = list(world.db.scalars(statement).all())
    if event_type is None:
        return rows
    return [row for row in rows if (row.metadata_json or {}).get("event_type") == event_type]


def test_application_status_change_notifies_candidate_and_staff(world: OfferWorld) -> None:
    service = _application_service(world)
    previous = world.application.status
    assert previous == ApplicationStatus.INTERVIEW.value

    updated = service.update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.REJECTED.value,
    )
    assert updated.status == ApplicationStatus.REJECTED.value

    candidate_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.APPLICATION_STATUS_CHANGED.value,
    )
    assert len(candidate_rows) == 1
    candidate_note = candidate_rows[0]
    assert candidate_note.category == NotificationCategory.APPLICATION.value
    assert "Backend Engineer" in (candidate_note.message or "")
    meta = candidate_note.metadata_json or {}
    assert meta["status"] == ApplicationStatus.REJECTED.value
    assert meta["previous_status"] == previous
    assert "ai" not in meta
    assert "score" not in meta
    assert "recommendation" not in meta
    assert "internal_secret" not in meta

    staff_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.APPLICATION_STATUS_CHANGED.value,
    )
    assert len(staff_rows) == 1
    assert staff_rows[0].company_id == world.company.id

    hm_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.hiring_manager.id,
        event_type=NotificationEventType.APPLICATION_STATUS_CHANGED.value,
    )
    assert len(hm_rows) == 1


def test_application_status_idempotent_no_duplicate_notification(world: OfferWorld) -> None:
    service = _application_service(world)
    service.update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.REJECTED.value,
    )
    first_count = len(
        _rows_for(
            world,
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=world.candidate.id,
            event_type=NotificationEventType.APPLICATION_STATUS_CHANGED.value,
        )
    )
    # Same status is a no-op (idempotent domain path).
    service.apply_status_transition(
        company_id=world.company.id,
        application_id=world.application.id,
        new_status=ApplicationStatus.REJECTED.value,
    )
    second_count = len(
        _rows_for(
            world,
            recipient_type=NotificationRecipientType.CANDIDATE,
            recipient_id=world.candidate.id,
            event_type=NotificationEventType.APPLICATION_STATUS_CHANGED.value,
        )
    )
    assert first_count == 1
    assert second_count == 1


def test_application_notification_failure_does_not_corrupt_status(
    world: OfferWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _application_service(world)
    assert service.notification_events is not None

    def _boom(*_args, **_kwargs):
        raise RuntimeError("notification store unavailable")

    monkeypatch.setattr(
        service.notification_events.notification_service,
        "create_notification",
        _boom,
    )

    updated = service.update_application_status(
        world.recruiter,
        world.application.id,
        ApplicationStatus.REJECTED.value,
    )
    assert updated.status == ApplicationStatus.REJECTED.value
    world.db.refresh(world.application)
    assert world.application.status == ApplicationStatus.REJECTED.value
    assert (
        len(
            _rows_for(
                world,
                recipient_type=NotificationRecipientType.CANDIDATE,
                recipient_id=world.candidate.id,
            )
        )
        == 0
    )


def test_interview_scheduled_notifies_candidate_and_interviewer(world: OfferWorld) -> None:
    service = _interview_service(world)
    start = datetime.now(timezone.utc) + timedelta(days=2)
    created = service.create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.hm_member.id,
            interview_type=InterviewType.TECHNICAL,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            timezone="UTC",
            meeting_link="https://meet.example/test",
        ),
    )

    candidate_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.INTERVIEW_SCHEDULED.value,
    )
    assert len(candidate_rows) == 1
    assert candidate_rows[0].entity_id == created.id
    assert "interview" in (candidate_rows[0].message or "").lower()
    assert "notes" not in (candidate_rows[0].metadata_json or {})

    interviewer_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.hiring_manager.id,
        event_type=NotificationEventType.INTERVIEW_SCHEDULED.value,
    )
    assert len(interviewer_rows) == 1
    assert interviewer_rows[0].company_id == world.company.id

    other_company_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.other_recruiter.id,
        event_type=NotificationEventType.INTERVIEW_SCHEDULED.value,
    )
    assert other_company_rows == []

    other_candidate_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.other_candidate.id,
        event_type=NotificationEventType.INTERVIEW_SCHEDULED.value,
    )
    assert other_candidate_rows == []


def test_interview_status_change_notifies_recipients(world: OfferWorld) -> None:
    service = _interview_service(world)
    start = datetime.now(timezone.utc) + timedelta(days=3)
    created = service.create_interview(
        world.recruiter,
        InterviewCreate(
            application_id=world.application.id,
            interviewer_member_id=world.hm_member.id,
            interview_type=InterviewType.PHONE,
            scheduled_start=start,
            scheduled_end=start + timedelta(minutes=30),
            timezone="UTC",
        ),
    )
    service.update_interview(
        world.recruiter,
        created.id,
        InterviewUpdate(status=InterviewStatus.CANCELLED),
    )

    candidate_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.INTERVIEW_CANCELLED.value,
    )
    assert len(candidate_rows) == 1
    interviewer_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.hiring_manager.id,
        event_type=NotificationEventType.INTERVIEW_CANCELLED.value,
    )
    assert len(interviewer_rows) == 1


def test_offer_created_notifies_staff_not_candidate(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    staff_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.OFFER_CREATED.value,
    )
    assert len(staff_rows) == 1
    assert staff_rows[0].entity_id == created.id
    assert staff_rows[0].company_id == world.company.id

    candidate_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.OFFER_CREATED.value,
    )
    assert candidate_rows == []

    other_staff = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.other_recruiter.id,
        event_type=NotificationEventType.OFFER_CREATED.value,
    )
    assert other_staff == []


def test_offer_accept_and_decline_notify_staff(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)

    candidate_approved = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.OFFER_APPROVED.value,
    )
    assert len(candidate_approved) == 1

    accepted = world.offer_service.accept_offer(world.candidate, approved.id)
    assert accepted.status == OfferStatus.ACCEPTED.value
    staff_accepted = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.OFFER_ACCEPTED.value,
    )
    assert len(staff_accepted) == 1


def test_offer_decline_and_withdraw_notifications(world: OfferWorld) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)

    declined = world.offer_service.decline_offer(world.candidate, approved.id, reason="timing")
    assert declined.status == OfferStatus.DECLINED.value
    staff_declined = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.hiring_manager.id,
        event_type=NotificationEventType.OFFER_DECLINED.value,
    )
    assert len(staff_declined) == 1

    # Revised offer path after decline
    revised = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted2 = world.offer_service.submit_for_approval(world.recruiter, revised.id)
    approved2 = world.offer_service.approve_offer(world.hiring_manager, submitted2.id)
    withdrawn = world.offer_service.withdraw_offer(world.recruiter, approved2.id, reason="budget")
    assert withdrawn.status == OfferStatus.WITHDRAWN.value

    candidate_withdrawn = _rows_for(
        world,
        recipient_type=NotificationRecipientType.CANDIDATE,
        recipient_id=world.candidate.id,
        event_type=NotificationEventType.OFFER_WITHDRAWN.value,
    )
    assert len(candidate_withdrawn) == 1
    staff_withdrawn = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.OFFER_WITHDRAWN.value,
    )
    assert len(staff_withdrawn) == 1


def test_offer_lifecycle_idempotent_accept_does_not_duplicate(
    world: OfferWorld,
) -> None:
    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    submitted = world.offer_service.submit_for_approval(world.recruiter, created.id)
    approved = world.offer_service.approve_offer(world.hiring_manager, submitted.id)
    world.offer_service.accept_offer(world.candidate, approved.id)

    with pytest.raises(ValueError):
        world.offer_service.accept_offer(world.candidate, approved.id)

    accepted_rows = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.OFFER_ACCEPTED.value,
    )
    assert len(accepted_rows) == 1


def test_offer_notification_failure_does_not_corrupt_offer(
    world: OfferWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert world.offer_service.notification_events is not None

    def _boom(*_args, **_kwargs):
        raise RuntimeError("notification unavailable")

    monkeypatch.setattr(
        world.offer_service.notification_events.notification_service,
        "create_notification",
        _boom,
    )

    created = world.offer_service.create_offer_for_application(
        world.recruiter,
        world.application.id,
        world.offer_payload(),
    )
    assert created.status == OfferStatus.DRAFT.value
    assert created.id is not None
    assert (
        len(
            _rows_for(
                world,
                recipient_type=NotificationRecipientType.USER,
                recipient_id=world.recruiter.id,
                event_type=NotificationEventType.OFFER_CREATED.value,
            )
        )
        == 0
    )


def test_cross_company_offer_does_not_notify_foreign_staff(world: OfferWorld) -> None:
    foreign = world.offer_service.create_offer_for_application(
        world.other_recruiter,
        world.other_application.id,
        world.offer_payload(application_id=world.other_application.id),
    )
    assert foreign.id is not None

    acme_staff = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.recruiter.id,
        event_type=NotificationEventType.OFFER_CREATED.value,
    )
    assert acme_staff == []

    other_staff = _rows_for(
        world,
        recipient_type=NotificationRecipientType.USER,
        recipient_id=world.other_recruiter.id,
        event_type=NotificationEventType.OFFER_CREATED.value,
    )
    assert len(other_staff) == 1
    assert other_staff[0].company_id == world.other_company.id
