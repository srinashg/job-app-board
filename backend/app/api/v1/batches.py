"""The five-job batch loop: view, apply, skip, save, unlock the next batch."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import DbSession, OnboardedUser
from app.models.enums import ApplicationStatus, BatchStatus, RecommendationStatus
from app.models.job import Job
from app.models.recommendation import Batch, Recommendation
from app.models.resume import Resume
from app.schemas.application import ApplicationRead
from app.schemas.common import Message
from app.schemas.matching import MatchResult
from app.schemas.recommendation import (
    ApplyRequest,
    BatchRead,
    BatchState,
    RecommendationRead,
    SkipRequest,
)
from app.services.applications import create_application
from app.services.recommendations import (
    batch_state,
    complete_batch_if_done,
    ensure_active_batch,
    get_active_resume,
    rank_candidates,
    resolve_recommendation,
)

router = APIRouter(prefix="/batches", tags=["batches"])


def _serialize_recommendation(recommendation: Recommendation) -> RecommendationRead:
    return RecommendationRead(
        id=recommendation.id,
        job_id=recommendation.job_id,
        batch_id=recommendation.batch_id,
        position=recommendation.position,
        status=recommendation.status,
        match_score=recommendation.match_score,
        skip_reason=recommendation.skip_reason,
        skip_note=recommendation.skip_note,
        resolved_at=recommendation.resolved_at,
        job=recommendation.job,
        match_explanation=(
            MatchResult.model_validate(recommendation.match_explanation)
            if recommendation.match_explanation
            else None
        ),
    )


def _serialize_batch(batch: Batch) -> BatchRead:
    return BatchRead(
        id=batch.id,
        sequence=batch.sequence,
        size=batch.size,
        status=batch.status,
        completed_at=batch.completed_at,
        created_at=batch.created_at,
        recommendations=[
            _serialize_recommendation(rec)
            for rec in sorted(batch.live_recommendations, key=lambda item: item.position)
        ],
        resolved_count=batch.resolved_count,
        is_complete=batch.is_complete,
    )


def _state_response(db: DbSession, user) -> BatchState:
    batch, can_unlock, exhausted = batch_state(db, user)
    if batch is not None:
        remaining = sum(1 for rec in batch.live_recommendations if not rec.is_resolved)
        return BatchState(
            batch=_serialize_batch(batch),
            can_unlock_next=False,
            remaining=remaining,
            exhausted=False,
            message=None,
        )
    return BatchState(
        batch=None,
        can_unlock_next=can_unlock,
        remaining=0,
        exhausted=exhausted,
        message=(
            "No jobs match your filters right now. Widen your preferences or check back "
            "after the next job fetch."
            if exhausted
            else "Your batch is complete. Unlock the next five jobs when you are ready."
        ),
    )


def _get_recommendation(db: DbSession, user_id: uuid.UUID, recommendation_id: uuid.UUID) -> Recommendation:
    recommendation = db.execute(
        select(Recommendation)
        .where(Recommendation.id == recommendation_id, Recommendation.user_id == user_id)
        .options(
            selectinload(Recommendation.job).selectinload(Job.company),
            selectinload(Recommendation.batch),
        )
    ).scalar_one_or_none()
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        )
    return recommendation


def _guard_resolved(recommendation: Recommendation) -> None:
    if recommendation.is_resolved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This job is already resolved ({recommendation.status})",
        )
    if recommendation.status == RecommendationStatus.REPLACED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This job was replaced in your batch",
        )


@router.get("/current", response_model=BatchState)
def read_current_batch(user: OnboardedUser, db: DbSession) -> BatchState:
    """The active batch, or what to do when there isn't one."""
    return _state_response(db, user)


@router.post("/next", response_model=BatchState)
def unlock_next_batch(user: OnboardedUser, db: DbSession) -> BatchState:
    """Unlock the next five jobs. Refused while the current batch is unfinished."""
    batch, _, _ = batch_state(db, user)
    if batch is not None and batch.status == BatchStatus.ACTIVE.value:
        remaining = sum(1 for rec in batch.live_recommendations if not rec.is_resolved)
        if remaining:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Resolve the {remaining} remaining job"
                    f"{'s' if remaining != 1 else ''} in your current batch first"
                ),
            )
        complete_batch_if_done(db, batch)

    new_batch = ensure_active_batch(db, user)
    if new_batch is None:
        return BatchState(
            batch=None,
            can_unlock_next=False,
            remaining=0,
            exhausted=True,
            message=(
                "No jobs match your filters right now. Widen your preferences or check "
                "back after the next job fetch."
            ),
        )
    return BatchState(
        batch=_serialize_batch(new_batch),
        can_unlock_next=False,
        remaining=sum(1 for rec in new_batch.live_recommendations if not rec.is_resolved),
    )


@router.get("/history", response_model=list[BatchRead])
def list_batches(user: OnboardedUser, db: DbSession) -> list[BatchRead]:
    stmt = (
        select(Batch)
        .where(Batch.user_id == user.id)
        .options(
            selectinload(Batch.recommendations)
            .selectinload(Recommendation.job)
            .selectinload(Job.company)
        )
        .order_by(Batch.sequence.desc())
    )
    return [_serialize_batch(batch) for batch in db.execute(stmt).scalars()]


@router.post("/recommendations/{recommendation_id}/apply", response_model=ApplicationRead)
def apply_to_job(
    recommendation_id: uuid.UUID,
    payload: ApplyRequest,
    user: OnboardedUser,
    db: DbSession,
) -> ApplicationRead:
    """Mark a recommendation applied and open a tracked application for it."""
    recommendation = _get_recommendation(db, user.id, recommendation_id)
    _guard_resolved(recommendation)

    resume = None
    if payload.resume_id is not None:
        resume = db.get(Resume, payload.resume_id)
        if resume is None or resume.user_id != user.id or resume.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found"
            )
    else:
        resume = get_active_resume(db, user.id)

    application = create_application(
        db,
        user,
        job=recommendation.job,
        resume=resume,
        application_url=payload.application_url,
        status=ApplicationStatus.APPLIED.value,
        notes=payload.notes,
        match_score=recommendation.match_score,
    )
    resolve_recommendation(
        db, user, recommendation, status=RecommendationStatus.APPLIED.value
    )
    return ApplicationRead.model_validate(application)


@router.post("/recommendations/{recommendation_id}/skip", response_model=BatchState)
def skip_job(
    recommendation_id: uuid.UUID,
    payload: SkipRequest,
    user: OnboardedUser,
    db: DbSession,
) -> BatchState:
    """Skip a job with a reason. Some reasons pull a replacement into the batch."""
    recommendation = _get_recommendation(db, user.id, recommendation_id)
    _guard_resolved(recommendation)
    resolve_recommendation(
        db,
        user,
        recommendation,
        status=RecommendationStatus.SKIPPED.value,
        skip_reason=payload.reason.value,
        skip_note=payload.note,
    )
    return _state_response(db, user)


@router.post("/recommendations/{recommendation_id}/save", response_model=RecommendationRead)
def save_job(
    recommendation_id: uuid.UUID, user: OnboardedUser, db: DbSession
) -> RecommendationRead:
    """Save a job for later. It still counts as unresolved in the batch."""
    recommendation = _get_recommendation(db, user.id, recommendation_id)
    _guard_resolved(recommendation)
    recommendation.status = RecommendationStatus.SAVED.value
    db.flush()
    return _serialize_recommendation(recommendation)


@router.post("/recommendations/{recommendation_id}/unsave", response_model=RecommendationRead)
def unsave_job(
    recommendation_id: uuid.UUID, user: OnboardedUser, db: DbSession
) -> RecommendationRead:
    recommendation = _get_recommendation(db, user.id, recommendation_id)
    if recommendation.status != RecommendationStatus.SAVED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This job is not saved"
        )
    recommendation.status = RecommendationStatus.ACTIVE.value
    db.flush()
    return _serialize_recommendation(recommendation)


@router.get("/saved", response_model=list[RecommendationRead])
def list_saved(user: OnboardedUser, db: DbSession) -> list[RecommendationRead]:
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.user_id == user.id,
            Recommendation.status == RecommendationStatus.SAVED.value,
        )
        .options(selectinload(Recommendation.job).selectinload(Job.company))
        .order_by(Recommendation.updated_at.desc())
    )
    return [_serialize_recommendation(rec) for rec in db.execute(stmt).scalars()]


@router.get("/preview", response_model=list[RecommendationRead])
def preview_matches(user: OnboardedUser, db: DbSession) -> list[RecommendationRead]:
    """Score the pool without consuming it, so filter changes show their effect."""
    candidates = rank_candidates(db, user, limit=10)
    return [
        RecommendationRead(
            id=uuid.uuid4(),
            job_id=candidate.job.id,
            batch_id=None,
            position=index,
            status="preview",
            match_score=candidate.result.score,
            job=candidate.job,
            match_explanation=candidate.result,
        )
        for index, candidate in enumerate(candidates)
    ]


@router.delete("/current", response_model=BatchState)
def discard_current_batch(user: OnboardedUser, db: DbSession) -> BatchState:
    """Rebuild the batch so changed filters take effect immediately.

    Jobs already resolved keep their outcome; the unresolved ones are released
    back into the pool and a fresh batch is built under the new filters.
    """
    batch, _, _ = batch_state(db, user)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="There is no active batch"
        )
    for recommendation in list(batch.recommendations):
        if not recommendation.is_resolved:
            db.delete(recommendation)
    batch.status = BatchStatus.COMPLETED.value
    batch.completed_at = datetime.now(timezone.utc)
    db.flush()

    rebuilt = ensure_active_batch(db, user)
    if rebuilt is None:
        return BatchState(
            batch=None,
            can_unlock_next=False,
            remaining=0,
            exhausted=True,
            message=(
                "No jobs match your filters right now. Widen your preferences or check "
                "back after the next job fetch."
            ),
        )
    return BatchState(
        batch=_serialize_batch(rebuilt),
        can_unlock_next=False,
        remaining=sum(1 for rec in rebuilt.live_recommendations if not rec.is_resolved),
    )
