"""Simple factory placeholders for tests.

These are lightweight placeholders; integrate with `factory_boy` or similar libraries as needed.
"""
from __future__ import annotations

from typing import Dict, Any
import time


class UserFactory:
    @staticmethod
    def build(**overrides) -> Dict[str, Any]:
        data = {
            "id": overrides.get("id", f"user-{int(time.time() * 1000)}"),
            "email": overrides.get("email", "test@example.com"),
            "is_active": overrides.get("is_active", True),
        }
        data.update(overrides)
        return data


class JobFactory:
    @staticmethod
    def build(**overrides) -> Dict[str, Any]:
        data = {"id": overrides.get("id", f"job-{int(time.time() * 1000)}"), "title": overrides.get("title", "Test Job")}
        data.update(overrides)
        return data
