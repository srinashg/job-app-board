"""Thin HTTP wrapper for source connectors, easy to stub in tests."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import settings


class HttpFetcher(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        ...

    def head_ok(self, url: str) -> bool | None:
        ...


class HttpxFetcher:
    """Default fetcher. Identifies itself and follows the source's redirects."""

    def __init__(self, timeout: float | None = None, user_agent: str | None = None) -> None:
        self._timeout = timeout or settings.ingest_request_timeout
        self._headers = {
            "User-Agent": user_agent or settings.ingest_user_agent,
            "Accept": "application/json, text/html;q=0.8",
        }

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def head_ok(self, url: str) -> bool | None:
        """``True`` if the listing URL still resolves, ``False`` on 404/410."""
        try:
            with httpx.Client(
                timeout=self._timeout, headers=self._headers, follow_redirects=True
            ) as client:
                response = client.head(url)
                if response.status_code == 405:
                    response = client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code in (404, 410):
            return False
        if response.is_success:
            return True
        return None
