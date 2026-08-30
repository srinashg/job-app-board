"""Ashby job-board connector (public posting API)."""

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

BOARD_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


class AshbyClient:
    source_type = SourceType.ASHBY.value

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpxFetcher()

    def fetch(self, external_slug: str, limit: int = 100) -> list[RawJob]:
        payload = self._fetcher.get_json(
            BOARD_API.format(slug=external_slug), params={"includeCompensation": "true"}
        )
        postings = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
        return [self._to_raw_job(item, external_slug) for item in postings[:limit]]

    def _to_raw_job(self, item: dict[str, Any], slug: str) -> RawJob:
        location = item.get("location")
        description = clean_description(
            item.get("descriptionPlain") or item.get("descriptionHtml") or ""
        )
        city, region, country = split_location(location)
        is_remote = bool(item.get("isRemote"))
        compensation = item.get("compensation") or {}
        summary = compensation.get("compensationTierSummary")
        return RawJob(
            external_id=str(item.get("id")),
            title=(item.get("title") or "").strip(),
            description=description,
            source_url=item.get("jobUrl") or "",
            apply_url=item.get("applyUrl") or item.get("jobUrl"),
            company_name=slug.replace("-", " ").title(),
            location=location,
            city=city,
            region=region,
            country=country,
            work_arrangement="remote" if is_remote else infer_work_arrangement(location, description),
            date_posted=parse_iso_date(item.get("publishedAt") or item.get("updatedAt")),
            raw_payload={
                "provider": self.source_type,
                "board": slug,
                "id": item.get("id"),
                "compensation_summary": summary,
            },
        )

    def is_open(self, job_url: str, external_id: str, external_slug: str) -> bool | None:
        try:
            payload = self._fetcher.get_json(BOARD_API.format(slug=external_slug))
        except Exception:
            return self._fetcher.head_ok(job_url)
        jobs = (payload or {}).get("jobs", []) if isinstance(payload, dict) else []
        return any(str(job.get("id")) == str(external_id) for job in jobs)
