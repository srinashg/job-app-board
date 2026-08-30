"""Feature 5: duplicate detection, re-checks, closing dead listings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import JobStatus, RecommendationStatus
from app.models.job import Company, Job, JobSource
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services.dedupe import compute_fingerprint, find_duplicate
from app.services.freshness import (
    MAX_VERIFICATION_FAILURES,
    run_freshness_check,
    select_jobs_to_check,
)
from app.services.ingest.verifier import VerificationResult, classify_page_text
from app.services.ingestion import run_source, upsert_job
from app.services.ingest.base import RawJob
from app.services.recommendations import ensure_active_batch
from tests.conftest import make_job, make_resume


class StubVerifier:
    """Answers with a fixed verdict, or per-URL verdicts."""

    def __init__(self, verdict: bool | None = True, by_url: dict[str, bool | None] | None = None):
        self.verdict = verdict
        self.by_url = by_url or {}
        self.seen: list[str] = []

    def verify(self, url: str) -> VerificationResult:
        self.seen.append(url)
        value = self.by_url.get(url, self.verdict)
        return VerificationResult(is_open=value, method="stub")


def test_identical_postings_share_a_fingerprint() -> None:
    left = compute_fingerprint("acme-corp", "Senior Software Engineer", "San Francisco, CA")
    right = compute_fingerprint("acme-corp", "Software Engineer II", "San Francisco, CA")
    assert left == right  # seniority noise is stripped from the title

    other_place = compute_fingerprint("acme-corp", "Senior Software Engineer", "Austin, TX")
    assert left != other_place


def test_remote_locations_normalise_to_one_key() -> None:
    assert compute_fingerprint("acme", "Engineer", "Remote - US") == compute_fingerprint(
        "acme", "Engineer", "Remote (US)"
    )


def test_a_second_posting_of_the_same_role_is_flagged_duplicate(
    db: Session, company: Company
) -> None:
    original = make_job(db, company, title="Senior Backend Engineer")
    match = find_duplicate(
        db,
        company_id=company.id,
        fingerprint=original.fingerprint,
        title="Backend Engineer II",
        description=original.description,
    )
    assert match is not None
    assert match.job.id == original.id
    assert match.reason == "fingerprint"


def test_a_different_role_is_not_a_duplicate(db: Session, company: Company) -> None:
    make_job(db, company, title="Senior Backend Engineer")
    match = find_duplicate(
        db,
        company_id=company.id,
        fingerprint=compute_fingerprint(company.slug, "Product Designer", "San Francisco, CA"),
        title="Product Designer",
        description="Design product surfaces in Figma.",
    )
    assert match is None


def test_ingesting_a_cross_posted_job_marks_it_duplicate(
    db: Session, company: Company, source: JobSource
) -> None:
    original = make_job(db, company, title="Senior Backend Engineer")
    raw = RawJob(
        external_id="dup-1",
        title="Senior Backend Engineer",
        description=original.description,
        source_url="https://other-board.example/dup-1",
        company_name=company.name,
        location="San Francisco, CA",
    )
    job, outcome = upsert_job(db, source, raw)

    assert outcome == "duplicate"
    assert job.status == JobStatus.DUPLICATE.value
    assert job.duplicate_of_id == original.id


def test_a_closed_listing_is_marked_closed(db: Session, company: Company) -> None:
    job = make_job(db, company)
    stats = run_freshness_check(db, verifier=StubVerifier(verdict=False), force=True)

    db.refresh(job)
    assert stats.marked_closed == 1
    assert job.status == JobStatus.CLOSED.value
    assert job.closed_at is not None


def test_an_open_listing_refreshes_its_verified_timestamp(db: Session, company: Company) -> None:
    job = make_job(db, company)
    job.last_verified_at = datetime.now(timezone.utc) - timedelta(days=5)
    db.flush()

    stats = run_freshness_check(db, verifier=StubVerifier(verdict=True), force=True)
    db.refresh(job)

    assert stats.still_open == 1
    assert job.status == JobStatus.ACTIVE.value
    assert job.last_verified_at > datetime.now(timezone.utc) - timedelta(minutes=1)


def test_repeated_inconclusive_checks_eventually_close_the_job(
    db: Session, company: Company
) -> None:
    job = make_job(db, company)
    for _ in range(MAX_VERIFICATION_FAILURES):
        run_freshness_check(db, verifier=StubVerifier(verdict=None), force=True)
    db.refresh(job)

    assert job.verification_failures >= MAX_VERIFICATION_FAILURES
    assert job.status == JobStatus.CLOSED.value


def test_one_inconclusive_check_leaves_the_job_open(db: Session, company: Company) -> None:
    job = make_job(db, company)
    run_freshness_check(db, verifier=StubVerifier(verdict=None), force=True)
    db.refresh(job)
    assert job.status == JobStatus.ACTIVE.value
    assert job.verification_failures == 1


def test_closing_a_job_resolves_its_open_recommendations(
    db: Session, user: User, company: Company
) -> None:
    make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)
    batch = ensure_active_batch(db, user)
    assert batch is not None and len(batch.recommendations) == 1

    run_freshness_check(db, verifier=StubVerifier(verdict=False), force=True)

    recommendation = db.execute(
        select(Recommendation).where(Recommendation.job_id == job.id)
    ).scalar_one()
    assert recommendation.status == RecommendationStatus.CLOSED.value
    assert recommendation.resolved_at is not None


def test_recheck_interval_is_respected_unless_forced(db: Session, company: Company) -> None:
    job = make_job(db, company)
    job.last_checked_at = datetime.now(timezone.utc)
    db.flush()

    assert select_jobs_to_check(db) == []
    assert select_jobs_to_check(db, force=True) == [job]


def test_long_unverified_jobs_go_stale(db: Session, company: Company) -> None:
    job = make_job(db, company)
    job.last_verified_at = datetime.now(timezone.utc) - timedelta(days=120)
    job.last_checked_at = datetime.now(timezone.utc)
    db.flush()

    stats = run_freshness_check(db, verifier=StubVerifier(verdict=True))
    db.refresh(job)
    assert stats.marked_stale == 1
    assert job.status == JobStatus.STALE.value


def test_page_text_classification_spots_closed_notices() -> None:
    assert classify_page_text("This position is no longer accepting applications").is_open is False
    assert classify_page_text("404 - Page Not Found").is_open is False
    assert classify_page_text("Apply now for this exciting role").is_open is True
    assert classify_page_text("").is_open is None
