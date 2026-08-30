"""Greenhouse job-board connector (public boards API)."""

from __future__ import annotations

from typing import Any

from app.models.enums import SourceType
from app.services.ingest.base import (
    RawJob,
    clean_description,
    infer_work_arrangement,
    parse_iso_date,
    split_location,
)
from app.services.ingest.http import HttpFetcher, HttpxFetcher

BOARD_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


class GreenhouseClient:
    source_type = SourceType.GREENHOUSE.value

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpxFetcher()

    def fetch(self, external_slug: str, limit: int = 100) -> list[RawJob]:
        payload = self._fetcher.get_json(
            BOARD_API.format(slug=external_slug), params={"content": "true"}
        )
        postings = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
        return [self._to_raw_job(item, external_slug) for item in postings[:limit]]

    def _to_raw_job(self, item: dict[str, Any], slug: str) -> RawJob:
        location = (item.get("location") or {}).get("name")
        description = clean_description(item.get("content"))
        city, region, country = split_location(location)
        offices = item.get("offices") or []
        street = None
        if offices and isinstance(offices[0], dict):
            street = offices[0].get("location")
        company_name = (item.get("company_name") or slug.replace("-", " ").title()).strip()
        return RawJob(
            external_id=str(item.get("id")),
            title=(item.get("title") or "").strip(),
            description=description,
            source_url=item.get("absolute_url") or "",
            apply_url=item.get("absolute_url"),
            company_name=company_name,
            location=location,
            city=city,
            region=region,
            country=country,
            street_address=street,
            work_arrangement=infer_work_arrangement(location, description),
            date_posted=parse_iso_date(item.get("updated_at") or item.get("first_published")),
            raw_payload={"provider": self.source_type, "board": slug, "id": item.get("id")},
        )

    def is_open(self, job_url: str, external_id: str, external_slug: str) -> bool | None:
        try:
            payload = self._fetcher.get_json(
                f"{BOARD_API.format(slug=external_slug)}/{external_id}"
            )
        except Exception:
            return self._fetcher.head_ok(job_url)
        return bool(payload and payload.get("id"))
