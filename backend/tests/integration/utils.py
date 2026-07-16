from __future__ import annotations

from typing import Any, Dict, List, Tuple
import json


class ExternalHTTPMock:
    """A lightweight HTTP mock that monkeypatches `httpx.request` and `httpx.AsyncClient.request`.

    Tests can register expected responses for specific (method, url) pairs.
    """

    def __init__(self):
        self._responses: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def register(self, method: str, url: str, status: int = 200, json_body: Any | None = None, text: str | None = None):
        self._responses[(method.upper(), url)] = {"status": status, "json": json_body, "text": text}

    def _find(self, method: str, url: str):
        return self._responses.get((method.upper(), url))

    def patch(self, monkeypatch):
        try:
            import httpx

            def _sync_request(method, url, *args, **kwargs):
                meta = self._find(method, str(url))
                if not meta:
                    raise RuntimeError(f"No mock registered for {method} {url}")
                if meta.get("json") is not None:
                    content = json.dumps(meta["json"]).encode("utf-8")
                else:
                    content = (meta.get("text") or "").encode("utf-8")
                return httpx.Response(meta["status"], content=content)

            async def _async_request(self_client, method, url, *args, **kwargs):
                meta = self._find(method, str(url))
                if not meta:
                    raise RuntimeError(f"No mock registered for {method} {url}")
                if meta.get("json") is not None:
                    return httpx.Response(meta["status"], json=meta["json"])
                return httpx.Response(meta["status"], content=(meta.get("text") or ""))

            monkeypatch.setattr(httpx, "request", _sync_request)
            monkeypatch.setattr(httpx.AsyncClient, "request", _async_request, raising=False)
        except Exception:
            # httpx not installed or monkeypatch not available; tests can handle this
            pass
