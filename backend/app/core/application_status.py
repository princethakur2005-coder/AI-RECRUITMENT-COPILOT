from __future__ import annotations

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Lifecycle statuses for job applications."""

    APPLIED = "applied"
    SCREENING = "screening"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"


DEFAULT_APPLICATION_STATUS = ApplicationStatus.APPLIED

PIPELINE_STATUSES: tuple[ApplicationStatus, ...] = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.SCREENING,
    ApplicationStatus.SHORTLISTED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFERED,
    ApplicationStatus.HIRED,
    ApplicationStatus.REJECTED,
)

ALLOWED_STATUS_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: frozenset({ApplicationStatus.SCREENING, ApplicationStatus.REJECTED}),
    ApplicationStatus.SCREENING: frozenset({ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED}),
    ApplicationStatus.SHORTLISTED: frozenset({ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED}),
    ApplicationStatus.INTERVIEW: frozenset({ApplicationStatus.OFFERED, ApplicationStatus.REJECTED}),
    # OFFERED -> INTERVIEW: current offer failed (withdrawn/rejected/declined); not a terminal reject.
    # Enables a legitimate revised offer on the same Application without a new status.
    ApplicationStatus.OFFERED: frozenset(
        {ApplicationStatus.HIRED, ApplicationStatus.REJECTED, ApplicationStatus.INTERVIEW}
    ),
    ApplicationStatus.HIRED: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
}


def validate_status_transition(current_status: str, new_status: str) -> ApplicationStatus:
    current = ApplicationStatus(current_status)
    new = ApplicationStatus(new_status)
    if current == new:
        raise ValueError("Application already has this status")
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValueError(f"Invalid status transition from '{current}' to '{new}'")
    return new
