from __future__ import annotations

from email.utils import parseaddr
from typing import Any


def is_valid_email(value: str) -> bool:
    _, address = parseaddr(value)
    return "@" in address and "." in address.split("@")[-1]


def ensure_non_empty(value: str | None, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value.strip()


def ensure_positive_int(value: int | None, field_name: str) -> int:
    if value is None or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def validate_payload(payload: dict[str, Any], required_fields: list[str]) -> None:
    for field in required_fields:
        if field not in payload or payload[field] in (None, ""):
            raise ValueError(f"Missing required field: {field}")
