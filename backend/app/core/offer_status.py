from __future__ import annotations

from enum import StrEnum


class OfferStatus(StrEnum):
    """Single production status contract for application-owned offers."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


DEFAULT_OFFER_STATUS = OfferStatus.DRAFT

OFFER_STATUSES: tuple[OfferStatus, ...] = tuple(OfferStatus)

# Legacy persisted values that must normalize into the production contract.
OFFER_STATUS_ALIASES: dict[str, OfferStatus] = {
    "pending": OfferStatus.PENDING_APPROVAL,
}

ALLOWED_OFFER_STATUS_TRANSITIONS: dict[OfferStatus, frozenset[OfferStatus]] = {
    OfferStatus.DRAFT: frozenset({OfferStatus.PENDING_APPROVAL, OfferStatus.WITHDRAWN}),
    OfferStatus.PENDING_APPROVAL: frozenset(
        {OfferStatus.APPROVED, OfferStatus.REJECTED, OfferStatus.WITHDRAWN}
    ),
    OfferStatus.APPROVED: frozenset(
        {
            OfferStatus.ACCEPTED,
            OfferStatus.DECLINED,
            OfferStatus.EXPIRED,
            OfferStatus.WITHDRAWN,
        }
    ),
    OfferStatus.REJECTED: frozenset(),
    OfferStatus.ACCEPTED: frozenset(),
    OfferStatus.DECLINED: frozenset(),
    OfferStatus.EXPIRED: frozenset(),
    OfferStatus.WITHDRAWN: frozenset(),
}

ACTIVE_OFFER_STATUSES: frozenset[OfferStatus] = frozenset(
    {
        OfferStatus.DRAFT,
        OfferStatus.PENDING_APPROVAL,
        OfferStatus.APPROVED,
    }
)

TERMINAL_OFFER_STATUSES: frozenset[OfferStatus] = frozenset(
    {
        OfferStatus.REJECTED,
        OfferStatus.ACCEPTED,
        OfferStatus.DECLINED,
        OfferStatus.EXPIRED,
        OfferStatus.WITHDRAWN,
    }
)

# Hiring-decision recommendations that authorize offer creation/submission.
OFFER_ELIGIBLE_RECOMMENDATIONS: frozenset[str] = frozenset({"Strong Hire", "Hire"})


def normalize_offer_status(status: str) -> OfferStatus:
    raw = str(status or "").strip().lower()
    if raw in OFFER_STATUS_ALIASES:
        return OFFER_STATUS_ALIASES[raw]
    return OfferStatus(raw)


def validate_offer_status_transition(current_status: str, new_status: str) -> OfferStatus:
    current = normalize_offer_status(current_status)
    new = normalize_offer_status(new_status)
    if current == new:
        raise ValueError("Offer already has this status")
    allowed = ALLOWED_OFFER_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise ValueError(f"Invalid offer status transition from '{current}' to '{new}'")
    return new
