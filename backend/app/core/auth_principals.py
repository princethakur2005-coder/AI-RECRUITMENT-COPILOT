"""JWT principal types shared by recruiter and candidate authentication."""

from __future__ import annotations

PRINCIPAL_USER = "user"
PRINCIPAL_CANDIDATE = "candidate"

VALID_PRINCIPALS = frozenset({PRINCIPAL_USER, PRINCIPAL_CANDIDATE})


def normalize_principal(value: object | None) -> str:
    """Return a normalized principal; missing/legacy claims default to user."""
    if value is None or value == "":
        return PRINCIPAL_USER
    principal = str(value).strip().lower()
    if principal not in VALID_PRINCIPALS:
        raise ValueError("Invalid authentication principal")
    return principal
