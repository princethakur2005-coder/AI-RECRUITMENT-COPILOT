from __future__ import annotations

import os
from typing import Any

import httpx


class GeminiClient:
    """Lightweight reusable client for Google Gemini-like APIs.

    The client reads the API key from the environment when not provided explicitly.
    Environment variables supported (in order): `GEMINI_API_KEY`, `GOOGLE_GEMINI_API_KEY`.
    """

    DEFAULT_BASE_URL = "https://gemini.googleapis.com/v1"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GEMINI_API_KEY")
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_text(self, prompt: str, model: str = "gemini-1.0", **kwargs: Any) -> dict[str, Any]:
        """Generate text using a Gemini-compatible endpoint.

        This method is intentionally generic so it can be adapted to specific
        Gemini/Vertex endpoints without changing calling code.
        """
        if not self.api_key:
            return {
                "prompt": prompt,
                "content": "",
                "provider": "gemini",
                "model": model,
                "status": "no_api_key",
                "meta": {},
            }

        url = f"{self.base_url}/models/{model}:generateText"
        payload = {"prompt": prompt, **kwargs}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # keep broad to avoid coupling to specific httpx errors
            return {
                "prompt": prompt,
                "content": "",
                "provider": "gemini",
                "model": model,
                "status": "error",
                "meta": {"error": str(exc)},
            }

        # Attempt to normalize a common text content path; fall back to raw response
        content = ""
        if isinstance(data, dict):
            # Common keys to look for in Gemini/Vertex-like responses
            for k in ("text", "output", "content", "generated_text", "candidates"):
                if k in data:
                    content = data.get(k)
                    break

        return {
            "prompt": prompt,
            "content": content or data,
            "provider": "gemini",
            "model": model,
            "status": "ok",
            "meta": {"raw": data},
        }
