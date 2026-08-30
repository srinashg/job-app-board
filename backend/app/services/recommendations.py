"""Five-job batches: build them, resolve them, unlock the next one.

Rules the rest of the app depends on:

* a user has at most one ``ACTIVE`` batch at a time;
* a job is never recommended to the same user twice — the unique
  ``(user_id, job_id)`` constraint on :class:`Recommendation` enforces it, and
  candidate selection excludes anything already seen;
* the next batch only unlocks once every live recommendation in the current
  batch is applied, skipped or closed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.enums import (
    REPLACEABLE_SKIP_REASONS,
    BatchStatus,
    BlacklistScope,
    JobStatus,
    RecommendationStatus,
)
from app.models.job import Blacklist, Company, Job
from app.models.recommendation import Batch, Recommendation
from app.models.resume import Resume
from app.models.user import User
from app.schemas.matching import MatchResult
from app.services.matching import CandidateProfile, score_job

#: How many jobs to score per batch build. Scoring is cheap and in-process, but
#: this caps the work for users with a very large job pool.
CANDIDATE_POOL_LIMIT = 400


@dataclass
class ScoredCandidate:
    job: Job
    result: MatchResult


def get_active_resume(db: Session, user_id: uuid.UUID) -> Resume | None:
    """The resume matching reads: the default one, else the newest."""
    stmt = (
        select(Resume)
        .where(Resume.user_id == user_id, Resume.deleted_at.is_(None))
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def build_candidate_profile(db: Session, user: User) -> CandidateProfile:
    return CandidateProfile.build(
        eligibility=user.eligibility,
        preferences=user.preferences,
        resume=get_active_resume(db, user.id),
        profile=user.profile,
    )


def _blacklisted_values(db: Session) -> tuple[set[str], set[str]]:
    rows = list(db.execute(select(Blacklist)).scalars())
    companies = {row.value for row in rows if row.scope == BlacklistScope.COMPANY.value}
    domains = {row.value for row in rows if row.scope == BlacklistScope.DOMAIN.value}
    return companies, domains


def seen_job_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """Every job this user has already been shown, in any batch, ever."""
    stmt = select(Recommendation.job_id).where(Recommendation.user_id == user_id)
    return set(db.execute(stmt).scalars())


def candidate_jobs(db: Session, user: User, *, exclude: set[uuid.UUID]) -> list[Job]:
    """Open, non-duplicate, non-blacklisted jobs the user has not seen."""
    blacklisted_companies, blacklisted_domains = _blacklisted_values(db)
    stmt = (
        select(Job)
        .join(Company, Job.company_id == Company.id)
        .where(
            Job.status == JobStatus.ACTIVE.value,
            Job.duplicate_of_id.is_(None),
            Company.is_blacklisted.is_(False),
        )
        .options(selectinload(Job.company))
        .order_by(Job.date_posted.desc().nullslast(), Job.first_seen_at.desc())
        .limit(CANDIDATE_POOL_LIMIT + len(exclude))
    )
    if blacklisted_companies:
        stmt = stmt.where(Company.slug.notin_(blacklisted_companies))
    if blacklisted_domains:
        stmt = stmt.where(
            (Company.domain.is_(None)) | (Company.domain.notin_(blacklisted_domains))
        )
    jobs = [job for job in db.execute(stmt).scalars() if job.id not in exclude]
    return jobs[:CANDIDATE_POOL_LIMIT]


def rank_candidates(
    db: Session, user: User, *, exclude: set[uuid.UUID] | None = None, limit: int | None = None
) -> list[ScoredCandidate]:
    """Score the candidate pool and return the eligible jobs, best first."""
    excluded = set(exclude or set()) | seen_job_ids(db, user.id)
    profile = build_candidate_profile(db, user)
    threshold = user.preferences.match_threshold if user.preferences else 0

    scored: list[ScoredCandidate] = []
    for job in candidate_jobs(db, user, exclude=excluded):
        result = score_job(job, profile)
        if not result.eligible or result.score < threshold:
            continue
        scored.append(ScoredCandidate(job=job, result=result))

    scored.sort(key=lambda item: (-item.result.score, item.job.title))
    return scored[:limit] if limit else scored


def get_active_batch(db: Session, user_id: uuid.UUID) -> Batch | None:
    stmt = (
        select(Batch)
        .where(Batch.user_id == user_id, Batch.status == BatchStatus.ACTIVE.value)
        .options(
            selectinload(Batch.recommendations)
            .selectinload(Recommendation.job)
            .selectinload(Job.company)
        )
        .order_by(Batch.sequence.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _next_sequence(db: Session, user_id: uuid.UUID) -> int:
    highest = db.execute(
        select(func.max(Batch.sequence)).where(Batch.user_id == user_id)
    ).scalar()
    return (highest or 0) + 1


def create_batch(db: Session, user: User, *, size: int | None = None) -> Batch:
    """Create the next batch and fill it with the top-scoring unseen jobs."""
    size = size or settings.batch_size
    batch = Batch(
        user_id=user.id,
        sequence=_next_sequence(db, user.id),
        size=size,
        status=BatchStatus.ACTIVE.value,
    )
    db.add(batch)
    db.flush()

    for position, candidate in enumerate(rank_candidates(db, user, limit=size)):
        db.add(
            Recommendation(
                user_id=user.id,
                job_id=candidate.job.id,
                batch_id=batch.id,
                position=position,
                status=RecommendationStatus.ACTIVE.value,
                match_score=candidate.result.score,
                match_explanation=candidate.result.model_dump(mode="json"),
            )
        )
    db.flush()
    db.refresh(batch)
    return batch


def ensure_active_batch(db: Session, user: User) -> Batch | None:
    """Return the live batch, creating one when the user has none."""
    batch = get_active_batch(db, user.id)
    if batch is not None:
        return batch
    batch = create_batch(db, user)
    if not batch.recommendations:
        # Nothing eligible right now; drop the empty shell so the next attempt
        # does not have to reconcile a stale, unfillable batch.
        db.delete(batch)
        db.flush()
        return None
    return batch


def complete_batch_if_done(db: Session, batch: Batch) -> bool:
    """Mark the batch completed once every live recommendation is resolved."""
    if batch.status != BatchStatus.ACTIVE.value or not batch.is_complete:
        return False
    batch.status = BatchStatus.COMPLETED.value
    batch.completed_at = datetime.now(timezone.utc)
    db.flush()
    return True


def replace_recommendation(
    db: Session, user: User, recommendation: Recommendation
) -> Recommendation | None:
    """Swap in a fresh job for one that turned out to be unavailable.

    Used when a job closes or the user skips it as already-applied/closed: the
    batch should still ask for five real decisions.
    """
    batch = recommendation.batch
    if batch is None or batch.status != BatchStatus.ACTIVE.value:
        return None

    candidates = rank_candidates(db, user, limit=1)
    if not candidates:
        return None

    candidate = candidates[0]
    replacement = Recommendation(
        user_id=user.id,
        job_id=candidate.job.id,
        batch_id=batch.id,
        position=recommendation.position,
        status=RecommendationStatus.ACTIVE.value,
        match_score=candidate.result.score,
        match_explanation=candidate.result.model_dump(mode="json"),
        replaced_recommendation_id=recommendation.id,
    )
    # The original stops counting towards the batch; the replacement takes its
    # slot, so the user still resolves five distinct jobs.
    recommendation.status = RecommendationStatus.REPLACED.value
    recommendation.resolved_at = datetime.now(timezone.utc)
    db.add(replacement)
    db.flush()
    db.refresh(batch)
    return replacement


def resolve_recommendation(
    db: Session,
    user: User,
    recommendation: Recommendation,
    *,
    status: str,
    skip_reason: str | None = None,
    skip_note: str | None = None,
) -> Recommendation | None:
    """Apply a terminal status and, when warranted, backfill the slot.

    Returns the replacement recommendation when one was created.
    """
    recommendation.status = status
    recommendation.skip_reason = skip_reason
    recommendation.skip_note = skip_note
    recommendation.resolved_at = datetime.now(timezone.utc)
    db.flush()

    replacement = None
    should_replace = status == RecommendationStatus.CLOSED.value or (
        status == RecommendationStatus.SKIPPED.value
        and skip_reason in REPLACEABLE_SKIP_REASONS
    )
    if should_replace:
        replacement = replace_recommendation(db, user, recommendation)

    if recommendation.batch is not None:
        complete_batch_if_done(db, recommendation.batch)
    return replacement


def prune_unavailable(db: Session, batch: Batch, user: User) -> int:
    """Close out recommendations whose job stopped being recommendable.

    Called whenever the batch is read, so a job that closed since the batch was
    built never sits in front of the user as an actionable card.
    """
    replaced = 0
    for recommendation in list(batch.live_recommendations):
        if recommendation.is_resolved:
            continue
        job = recommendation.job
        if job is not None and job.is_recommendable:
            continue
        resolve_recommendation(
            db, user, recommendation, status=RecommendationStatus.CLOSED.value
        )
        replaced += 1
    return replaced


def has_any_batch(db: Session, user_id: uuid.UUID) -> bool:
    return db.execute(select(Batch.id).where(Batch.user_id == user_id).limit(1)).first() is not None


def batch_state(db: Session, user: User) -> tuple[Batch | None, bool, bool]:
    """Current batch, whether the next can unlock, and whether we ran dry.

    A user who has never had a batch gets their first one built here, so the
    board is populated on first visit. Every batch after that needs an explicit
    unlock, which is what makes the user resolve all five before moving on.
    """
    batch = get_active_batch(db, user.id)
    if batch is not None:
        prune_unavailable(db, batch, user)
        complete_batch_if_done(db, batch)
        if batch.status == BatchStatus.ACTIVE.value:
            return batch, False, False
    elif not has_any_batch(db, user.id):
        first = ensure_active_batch(db, user)
        if first is not None:
            return first, False, False
        return None, False, True

    # The previous batch just completed: the next one waits for an explicit unlock.
    exhausted = not rank_candidates(db, user, limit=1)
    return None, not exhausted, exhausted
