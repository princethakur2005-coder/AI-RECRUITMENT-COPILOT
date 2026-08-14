"""Notification domain enums — shared by model, schemas, and services."""

from __future__ import annotations

from enum import StrEnum


class NotificationRecipientType(StrEnum):
    USER = "user"
    CANDIDATE = "candidate"


class NotificationCategory(StrEnum):
    SYSTEM = "system"
    CANDIDATE = "candidate"
    INTERVIEW = "interview"
    EVALUATION = "evaluation"
    RECOMMENDATION = "recommendation"
    OFFER = "offer"
    APPLICATION = "application"
    CUSTOM = "custom"


class NotificationPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"


class NotificationEventType(StrEnum):
    """Explicit domain event contracts for the first producer group.

    Values are stored in notification metadata as ``event_type``.
    Only events that map to real Application / Interview / Offer lifecycle
    transitions are defined here — not a generic catch-all bus.
    """

    APPLICATION_STATUS_CHANGED = "application.status_changed"

    INTERVIEW_SCHEDULED = "interview.scheduled"
    INTERVIEW_COMPLETED = "interview.completed"
    INTERVIEW_CANCELLED = "interview.cancelled"
    INTERVIEW_NO_SHOW = "interview.no_show"

    OFFER_CREATED = "offer.created"
    OFFER_SUBMITTED = "offer.submitted"
    OFFER_APPROVED = "offer.approved"
    OFFER_REJECTED = "offer.rejected"
    OFFER_ACCEPTED = "offer.accepted"
    OFFER_DECLINED = "offer.declined"
    OFFER_WITHDRAWN = "offer.withdrawn"


# Interview status string → producer event (meaningful terminal/progress transitions).
INTERVIEW_STATUS_EVENT_MAP: dict[str, NotificationEventType] = {
    "completed": NotificationEventType.INTERVIEW_COMPLETED,
    "cancelled": NotificationEventType.INTERVIEW_CANCELLED,
    "no_show": NotificationEventType.INTERVIEW_NO_SHOW,
}

# Staff roles that receive company-scoped hiring lifecycle notifications.
NOTIFICATION_STAFF_ROLES: frozenset[str] = frozenset(
    {"company_admin", "recruiter", "hiring_manager"}
)

# First-pack email-eligible (event_type, recipient_type) pairs.
# Not every in-app notification is emailed — channel preferences apply after eligibility.
EMAIL_ELIGIBLE_EVENT_RECIPIENTS: frozenset[tuple[NotificationEventType, NotificationRecipientType]] = frozenset(
    {
        (NotificationEventType.INTERVIEW_SCHEDULED, NotificationRecipientType.CANDIDATE),
        # Candidate-facing offer availability (approved offer — not draft create/submit).
        (NotificationEventType.OFFER_APPROVED, NotificationRecipientType.CANDIDATE),
        (NotificationEventType.OFFER_ACCEPTED, NotificationRecipientType.USER),
        (NotificationEventType.OFFER_DECLINED, NotificationRecipientType.USER),
    }
)

# Categories that cannot be preference-disabled (always deliver when produced).
# No fabricated "security" events — only the existing SYSTEM category contract.
MANDATORY_NOTIFICATION_CATEGORIES: frozenset[NotificationCategory] = frozenset(
    {NotificationCategory.SYSTEM}
)

# Categories recipients may configure for in-app / email channels.
PREFERENCE_CONFIGURABLE_CATEGORIES: frozenset[NotificationCategory] = frozenset(
    {
        NotificationCategory.APPLICATION,
        NotificationCategory.INTERVIEW,
        NotificationCategory.OFFER,
        NotificationCategory.CANDIDATE,
        NotificationCategory.EVALUATION,
        NotificationCategory.RECOMMENDATION,
        NotificationCategory.CUSTOM,
    }
)
