from __future__ import annotations

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Lifecycle statuses for job applications."""

    APPLIED = "applied"
    SCREENING = "screening"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    INTERVIEW_COMPLETED = "interview_completed"
    DECISION_READY = "decision_ready"
    OFFER_PENDING = "offer_pending"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"


DEFAULT_APPLICATION_STATUS = ApplicationStatus.APPLIED

PIPELINE_STATUSES: tuple[ApplicationStatus, ...] = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.SHORTLISTED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.INTERVIEW_COMPLETED,
    ApplicationStatus.DECISION_READY,
    ApplicationStatus.OFFER_PENDING,
    ApplicationStatus.OFFERED,
    ApplicationStatus.HIRED,
    ApplicationStatus.REJECTED,
)

ALLOWED_STATUS_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: frozenset({ApplicationStatus.SCREENING, ApplicationStatus.REJECTED}),
    ApplicationStatus.SCREENING: frozenset({
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.INTERVIEW_COMPLETED,
        ApplicationStatus.DECISION_READY,
        ApplicationStatus.OFFER_PENDING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
    }),
    ApplicationStatus.SHORTLISTED: frozenset({
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.INTERVIEW_COMPLETED,
        ApplicationStatus.DECISION_READY,
        ApplicationStatus.OFFER_PENDING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
    }),
    ApplicationStatus.INTERVIEW: frozenset({
        ApplicationStatus.INTERVIEW_COMPLETED,
        ApplicationStatus.DECISION_READY,
        ApplicationStatus.OFFER_PENDING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
    }),
    ApplicationStatus.INTERVIEW_COMPLETED: frozenset({
        ApplicationStatus.DECISION_READY,
        ApplicationStatus.OFFER_PENDING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.INTERVIEW,
    }),
    ApplicationStatus.DECISION_READY: frozenset({
        ApplicationStatus.OFFER_PENDING,
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.INTERVIEW,
    }),
    ApplicationStatus.OFFER_PENDING: frozenset({
        ApplicationStatus.OFFERED,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.DECISION_READY,
        ApplicationStatus.INTERVIEW,
    }),
    # OFFERED -> INTERVIEW: current offer failed (withdrawn/rejected/declined); not a terminal reject.
    # Enables a legitimate revised offer on the same Application without a new status.
    ApplicationStatus.OFFERED: frozenset(
        {ApplicationStatus.HIRED, ApplicationStatus.REJECTED, ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER_PENDING}
    ),
    ApplicationStatus.HIRED: frozenset({ApplicationStatus.REJECTED}),
    ApplicationStatus.REJECTED: frozenset({ApplicationStatus.SCREENING, ApplicationStatus.INTERVIEW}),
}


def validate_status_transition(current_status: str, new_status: str) -> ApplicationStatus:
    curr_str = str(current_status).strip().lower()
    new_str = str(new_status).strip().lower()
    if curr_str == "offer":
        curr_str = ApplicationStatus.OFFERED.value
    if new_str == "offer":
        new_str = ApplicationStatus.OFFERED.value
    current = ApplicationStatus(curr_str)
    new = ApplicationStatus(new_str)
    if current == new:
        raise ValueError("Application already has this status")
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValueError(f"Invalid status transition from '{current}' to '{new}'")
    return new
