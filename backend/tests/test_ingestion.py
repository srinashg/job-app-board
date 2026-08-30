"""Feature 4: fetching jobs from career-site/ATS sources."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobSource
from app.services.ingest.base import (
    infer_work_arrangement,
    parse_citizenship_required,
    parse_min_years,
    parse_salary,
    parse_sponsorship,
    split_location,
)
from app.services.ingest.greenhouse import GreenhouseClient
from app.services.ingest.lever import LeverClient
from app.services.ingestion import run_ingestion, run_source

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 4001,
            "title": "Senior Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4001",
            "updated_at": "2026-08-01T12:00:00Z",
            "location": {"name": "San Francisco, CA"},
            "offices": [{"location": "500 Market St, San Francisco"}],
            "content": (
                "<p>We need a backend engineer.</p>"
                "<h3>Requirements</h3><ul><li>Python</li><li>PostgreSQL</li></ul>"
                "<h3>Nice to have</h3><ul><li>Kubernetes</li></ul>"
                "<p>5+ years of experience. $150,000 - $190,000. "
                "We are not able to provide visa sponsorship.</p>"
            ),
        },
        {
            "id": 4002,
            "title": "Data Analyst",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4002",
            "updated_at": "2026-08-02T12:00:00Z",
            "location": {"name": "Remote - US"},
            "content": "<p>Analyse data with SQL and Tableau.</p>",
        },
    ]
}

LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "Staff Platform Engineer",
        "hostedUrl": "https://jobs.lever.co/globex/abc-123",
        "applyUrl": "https://jobs.lever.co/globex/abc-123/apply",
        "createdAt": 1754006400000,
        "categories": {"location": "New York, NY"},
        "workplaceType": "hybrid",
        "descriptionPlain": "Run Kubernetes and Terraform. 8 years of experience required.",
        "lists": [{"text": "Requirements", "content": "<li>Go</li><li>AWS</li>"}],
    }
]


class StubFetcher:
    """Returns canned payloads so tests never touch the network."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(url)
        return self.payload

    def head_ok(self, url: str) -> bool | None:
        return True


class FailingFetcher:
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        raise RuntimeError("board is unreachable")

    def head_ok(self, url: str) -> bool | None:
        return None


def test_greenhouse_client_maps_the_payload() -> None:
    jobs = GreenhouseClient(fetcher=StubFetcher(GREENHOUSE_PAYLOAD)).fetch("acme")
    assert len(jobs) == 2

    first = jobs[0]
    assert first.external_id == "4001"
    assert first.title == "Senior Backend Engineer"
    assert first.source_url.endswith("/4001")
    assert first.city == "San Francisco"
    assert first.region == "CA"
    assert first.country == "US"
    assert first.street_address == "500 Market St, San Francisco"
    assert first.work_arrangement == "onsite"
    assert "<p>" not in first.description
    assert jobs[1].work_arrangement == "remote"


def test_lever_client_maps_the_payload() -> None:
    jobs = LeverClient(fetcher=StubFetcher(LEVER_PAYLOAD)).fetch("globex")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Staff Platform Engineer"
    assert job.work_arrangement == "hybrid"
    assert job.apply_url.endswith("/apply")
    assert "Go" in job.description  # list blocks are folded into the description


def test_run_source_persists_jobs_with_derived_fields(db: Session, source: JobSource) -> None:
    stats = run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    assert stats.jobs_fetched == 2
    assert stats.jobs_created == 2
    assert not stats.errors

    job = db.execute(select(Job).where(Job.external_id == "4001")).scalar_one()
    assert job.status == "active"
    assert job.salary_min == 150_000 and job.salary_max == 190_000
    assert job.min_years_experience == 5
    assert job.sponsorship_available is False
    assert "python" in job.required_skills
    assert "kubernetes" in job.preferred_skills
    assert job.description_snapshot == job.description
    assert job.first_seen_at is not None and job.last_verified_at is not None
    assert job.fingerprint

    db.refresh(source)
    assert source.last_fetch_status == "ok"
    assert source.jobs_seen == 2


def test_re_running_a_source_updates_rather_than_duplicates(
    db: Session, source: JobSource
) -> None:
    run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    second = run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))

    assert second.jobs_created == 0
    assert second.jobs_updated == 2
    assert db.execute(select(Job)).scalars().all().__len__() == 2


def test_a_relisted_job_reopens(db: Session, source: JobSource) -> None:
    run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    job = db.execute(select(Job).where(Job.external_id == "4001")).scalar_one()
    job.status = "closed"
    db.flush()

    run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    db.refresh(job)
    assert job.status == "active"
    assert job.closed_at is None


def test_the_description_snapshot_is_written_once(db: Session, source: JobSource) -> None:
    run_source(db, source, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    job = db.execute(select(Job).where(Job.external_id == "4002")).scalar_one()
    original_snapshot = job.description_snapshot

    changed = {
        "jobs": [
            {**GREENHOUSE_PAYLOAD["jobs"][1], "content": "<p>Rewritten description.</p>"}
        ]
    }
    run_source(db, source, fetcher=StubFetcher(changed))
    db.refresh(job)

    assert job.description == "Rewritten description."
    assert job.description_snapshot == original_snapshot


def test_a_source_failure_is_recorded_and_does_not_raise(
    db: Session, source: JobSource
) -> None:
    stats = run_source(db, source, fetcher=FailingFetcher())
    assert stats.jobs_fetched == 0
    assert stats.errors

    db.refresh(source)
    assert source.last_fetch_status == "error"
    assert "unreachable" in source.last_fetch_error


def test_run_ingestion_skips_disabled_sources(db: Session, source: JobSource) -> None:
    source.is_enabled = False
    db.flush()
    stats = run_ingestion(db, fetcher=StubFetcher(GREENHOUSE_PAYLOAD))
    assert stats.sources_run == 0


def test_salary_parsing() -> None:
    assert parse_salary("The range is $150,000 - $190,000 per year.") == (150_000, 190_000)
    assert parse_salary("We pay $120k to $160k.") == (120_000, 160_000)
    assert parse_salary("Competitive compensation.") == (None, None)
    # Hourly figures must not be read as an annual range.
    assert parse_salary("$25 - $35 per hour") == (None, None)


def test_experience_and_sponsorship_parsing() -> None:
    assert parse_min_years("Requires 7 years of professional experience") == 7
    assert parse_min_years("No specific requirement") is None
    assert parse_sponsorship("We are unable to sponsor visas") is False
    assert parse_sponsorship("Visa sponsorship is available") is True
    assert parse_sponsorship("Nothing said either way") is None
    assert parse_citizenship_required("Must be a US citizen") is True


def test_work_arrangement_inference() -> None:
    assert infer_work_arrangement("Remote - US", None) == "remote"
    assert infer_work_arrangement("Austin, TX (Hybrid)", None) == "hybrid"
    assert infer_work_arrangement("Austin, TX", None) == "onsite"
    assert infer_work_arrangement(None, "This role is fully remote.") == "remote"
    assert infer_work_arrangement(None, None) is None


def test_location_splitting() -> None:
    assert split_location("San Francisco, CA, USA") == ("San Francisco", "CA", "US")
    assert split_location("Berlin, Germany") == ("Berlin", None, "DE")
    assert split_location("Remote") == (None, None, None)
    assert split_location(None) == (None, None, None)
