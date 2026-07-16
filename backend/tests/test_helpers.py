"""Test helpers: common assertions and mock helpers."""
from __future__ import annotations

from typing import Any, Dict


def assert_json_ok(response: Any) -> Dict[str, Any]:
    assert response.status_code >= 200 and response.status_code < 300
    data = response.json()
    assert isinstance(data, dict)
    return data


class MockService:
    """Simple mock service placeholder to simulate external dependencies in tests."""

    def __init__(self):
        self.calls = []
        self.responses = []

    def enqueue_response(self, resp: Any) -> None:
        self.responses.append(resp)

    def call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return None
