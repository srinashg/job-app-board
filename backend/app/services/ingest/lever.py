"""Lever postings connector (public postings API)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.enums import SourceType
from app.services.ingest.base import (
    RawJob,
    clean_description,
    infer_work_arrangement,
    split_location,
)
from app.services.ingest.http import HttpFetcher, HttpxFetcher

POSTINGS_API = "https://api.lever.co/v0/postings/{slug}"


class LeverClient:
    source_type = SourceType.LEVER.value

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpxFetcher()

    def fetch(self, external_slug: str, limit: int = 100) -> list[RawJob]:
        payload = self._fetcher.get_json(
            POSTINGS_API.format(slug=external_slug), params={"mode": "json"}
        )
        postings = payload if isinstance(payload, list) else []
        return [self._to_raw_job(item, external_slug) for item in postings[:limit]]

    def _to_raw_job(self, item: dict[str, Any], slug: str) -> RawJob:
        categories = item.get("categories") or {}
        location = categories.get("location")
        description = clean_description(
            item.get("descriptionPlain") or item.get("description") or ""
        )
        lists_text = "\n".join(
            f"{block.get('text', '')}\n{clean_description(block.get('content'))}"
            for block in (item.get("lists") or [])
            if isinstance(block, dict)
        )
        full_description = "\n\n".join(part for part in (description, lists_text) if part.strip())
        city, region, country = split_location(location)
        posted_ms = item.get("createdAt")
        date_posted = None
        if isinstance(posted_ms, (int, float)):
            date_posted = datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc).date()
        workplace = (item.get("workplaceType") or "").lower() or None
        arrangement = workplace if workplace in {"remote", "hybrid", "onsite"} else None
        return RawJob(
            external_id=str(item.get("id")),
            title=(item.get("text") or "").strip(),
            description=full_description,
            source_url=item.get("hostedUrl") or "",
            apply_url=item.get("applyUrl") or item.get("hostedUrl"),
            company_name=slug.replace("-", " ").title(),
            location=location,
            city=city,
            region=region,
            country=country,
            work_arrangement=arrangement or infer_work_arrangement(location, full_description),
            date_posted=date_posted,
            raw_payload={"provider": self.source_type, "board": slug, "id": item.get("id")},
        )

    def is_open(self, job_url: str, external_id: str, external_slug: str) -> bool | None:
        try:
            payload = self._fetcher.get_json(
                f"{POSTINGS_API.format(slug=external_slug)}/{external_id}"
            )
        except Exception:
            return self._fetcher.head_ok(job_url)
        return bool(payload and payload.get("id"))
