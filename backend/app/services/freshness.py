"""Re-check listings, mark closed/stale jobs and keep recommendations honest."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.enums import JobStatus, RecommendationStatus
from app.models.job import Job
from app.models.recommendation import Recommendation
from app.services.ingest.verifier import JobVerifier

logger = logging.getLogger(__name__)

#: Consecutive inconclusive/failed checks before a job is treated as closed.
MAX_VERIFICATION_FAILURES = 3


@dataclass
class FreshnessStats:
    checked: int = 0
    still_open: int = 0
    marked_closed: int = 0
    marked_stale: int = 0
    errors: list[str] = field(default_factory=list)


def select_jobs_to_check(db: Session, *, limit: int = 50, force: bool = False) -> list[Job]:
    """Jobs whose recheck interval has elapsed, oldest check first."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.job_recheck_after_hours)
    stmt = (
        select(Job)
        .where(Job.status.in_([JobStatus.ACTIVE.value, JobStatus.STALE.value]))
        .order_by(Job.last_checked_at.asc().nullsfirst())
        .limit(limit)
    )
    if not force:
        stmt = stmt.where(or_(Job.last_checked_at.is_(None), Job.last_checked_at < cutoff))
    return list(db.execute(stmt).scalars())


def mark_job_closed(db: Session, job: Job, *, reason: str | None = None) -> None:
    """Close a job and resolve every active recommendation pointing at it."""
    now = datetime.now(timezone.utc)
    job.status = JobStatus.CLOSED.value
    job.closed_at = now
    job.last_checked_at = now
    if reason:
        job.moderation_notes = reason
    close_recommendations_for_job(db, job)


def close_recommendations_for_job(db: Session, job: Job) -> int:
    """Resolve active/saved recommendations for a job that is no longer open."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.job_id == job.id,
            Recommendation.status.in_(
                [RecommendationStatus.ACTIVE.value, RecommendationStatus.SAVED.value]
            ),
        )
        .options(selectinload(Recommendation.batch))
    )
    affected = list(db.execute(stmt).scalars())
    for recommendation in affected:
        recommendation.status = RecommendationStatus.CLOSED.value
        recommendation.resolved_at = now
    return len(affected)


def mark_stale_jobs(db: Session) -> int:
    """Age out listings we have not been able to re-verify for a long time."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.job_stale_after_days)
    stmt = select(Job).where(
        Job.status == JobStatus.ACTIVE.value,
        or_(Job.last_verified_at.is_(None), Job.last_verified_at < cutoff),
    )
    jobs = list(db.execute(stmt).scalars())
    for job in jobs:
        job.status = JobStatus.STALE.value
    return len(jobs)


def run_freshness_check(
    db: Session,
    *,
    limit: int = 50,
    force: bool = False,
    verifier: JobVerifier | None = None,
) -> FreshnessStats:
    """Verify a slice of listings and update their status."""
    verifier = verifier or JobVerifier()
    stats = FreshnessStats()
    now = datetime.now(timezone.utc)

    for job in select_jobs_to_check(db, limit=limit, force=force):
        stats.checked += 1
        try:
            result = verifier.verify(job.apply_url or job.source_url)
        except Exception as exc:  # a source outage must not abort the sweep
            logger.warning("Verification error for job %s: %s", job.id, exc)
            stats.errors.append(f"{job.id}: {exc}")
            job.last_checked_at = now
            continue

        job.last_checked_at = now
        if result.is_open is True:
            job.last_verified_at = now
            job.verification_failures = 0
            if job.status == JobStatus.STALE.value:
                job.status = JobStatus.ACTIVE.value
            stats.still_open += 1
        elif result.is_open is False:
            mark_job_closed(db, job, reason=result.detail)
            stats.marked_closed += 1
        else:
            job.verification_failures = (job.verification_failures or 0) + 1
            if job.verification_failures >= MAX_VERIFICATION_FAILURES:
                mark_job_closed(
                    db,
                    job,
                    reason=(
                        f"Closed after {job.verification_failures} inconclusive checks"
                        + (f": {result.detail}" if result.detail else "")
                    ),
                )
                stats.marked_closed += 1
            if result.detail:
                stats.errors.append(f"{job.id}: {result.detail}")

    stats.marked_stale = mark_stale_jobs(db)
    db.flush()
    return stats
