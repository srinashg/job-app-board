"""Playwright-backed verification that a listing is still live.

Career sites frequently keep the URL alive but replace the body with a "no
longer accepting applications" notice, which an HTTP status check cannot see.
Playwright renders the page and looks for those markers. It is optional: when
Playwright is unavailable the verifier falls back to an HTTP check.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.ingest.http import HttpFetcher, HttpxFetcher

logger = logging.getLogger(__name__)

CLOSED_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"no longer (?:accepting|available|open|being accepted)", re.IGNORECASE),
    re.compile(r"this (?:job|position|posting|role) (?:is|has been) (?:closed|filled|expired)", re.IGNORECASE),
    re.compile(r"position (?:has been )?(?:filled|closed)", re.IGNORECASE),
    re.compile(r"job (?:not found|has expired)", re.IGNORECASE),
    re.compile(r"posting (?:is )?(?:closed|expired|removed)", re.IGNORECASE),
    re.compile(r"we are no longer hiring for this", re.IGNORECASE),
    re.compile(r"404\s*[-–—:]?\s*(?:page )?not found", re.IGNORECASE),
)


@dataclass
class VerificationResult:
    #: ``True`` open, ``False`` closed, ``None`` could not tell.
    is_open: bool | None
    method: str
    detail: str | None = None


class JobVerifier:
    """Checks a posting URL, preferring a rendered page when Playwright is on."""

    def __init__(
        self,
        fetcher: HttpFetcher | None = None,
        *,
        use_playwright: bool | None = None,
        timeout_ms: int = 20_000,
    ) -> None:
        self._fetcher = fetcher or HttpxFetcher()
        self._use_playwright = (
            settings.playwright_enabled if use_playwright is None else use_playwright
        )
        self._timeout_ms = timeout_ms

    def verify(self, url: str) -> VerificationResult:
        if not url:
            return VerificationResult(is_open=None, method="none", detail="No source URL")
        if self._use_playwright:
            result = self._verify_with_playwright(url)
            if result.is_open is not None:
                return result
        status = self._fetcher.head_ok(url)
        return VerificationResult(
            is_open=status,
            method="http",
            detail=None if status is not None else "Source did not answer conclusively",
        )

    def _verify_with_playwright(self, url: str) -> VerificationResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.info("Playwright is not installed; falling back to HTTP verification")
            return VerificationResult(is_open=None, method="playwright-unavailable")

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(user_agent=settings.ingest_user_agent)
                    page = context.new_page()
                    response = page.goto(url, timeout=self._timeout_ms, wait_until="domcontentloaded")
                    if response is not None and response.status in (404, 410):
                        return VerificationResult(
                            is_open=False,
                            method="playwright",
                            detail=f"HTTP {response.status}",
                        )
                    body = page.inner_text("body", timeout=self._timeout_ms)
                finally:
                    browser.close()
        except Exception as exc:  # network/browser failures must not break a run
            logger.warning("Playwright verification failed for %s: %s", url, exc)
            return VerificationResult(is_open=None, method="playwright-error", detail=str(exc))

        return classify_page_text(body)


def classify_page_text(body: str | None) -> VerificationResult:
    """Decide whether rendered page text says the posting is closed."""
    if not body or not body.strip():
        return VerificationResult(is_open=None, method="playwright", detail="Empty page body")
    for marker in CLOSED_MARKERS:
        match = marker.search(body)
        if match:
            return VerificationResult(
                is_open=False, method="playwright", detail=f"Matched: {match.group(0)!r}"
            )
    return VerificationResult(is_open=True, method="playwright")
