"""Application tracker: creation from a recommendation, status history, stats."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    OPEN_PIPELINE_STATUSES,
    RESPONSE_STATUSES,
    ApplicationStatus,
    BatchStatus,
    RecommendationStatus,
    WorkArrangement,
)
from app.models.application import Application, ApplicationEvent
from app.models.job import Job
from app.models.recommendation import Batch, Recommendation
from app.models.resume import Resume
from app.models.user import User
from app.schemas.application import DashboardStats, StatusCount

#: Status transitions the tracker allows. Terminal states stay terminal except
#: for an explicit re-open back to ``todo``.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ApplicationStatus.TODO.value: {
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.SKIPPED.value,
        ApplicationStatus.CLOSED.value,
        ApplicationStatus.WITHDRAWN.value,
    },
    ApplicationStatus.APPLIED.value: {
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.OFFER.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
        ApplicationStatus.CLOSED.value,
    },
    ApplicationStatus.INTERVIEW.value: {
        ApplicationStatus.OFFER.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
        ApplicationStatus.CLOSED.value,
        ApplicationStatus.INTERVIEW.value,
    },
    ApplicationStatus.OFFER.value: {
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
        ApplicationStatus.CLOSED.value,
    },
    ApplicationStatus.REJECTED.value: {ApplicationStatus.TODO.value},
    ApplicationStatus.WITHDRAWN.value: {ApplicationStatus.TODO.value},
    ApplicationStatus.SKIPPED.value: {ApplicationStatus.TODO.value},
    ApplicationStatus.CLOSED.value: {ApplicationStatus.TODO.value},
}


class TransitionError(ValueError):
    """Raised for a status change the tracker does not allow."""


def can_transition(current: str, target: str) -> bool:
    if current == target:
        return target == ApplicationStatus.INTERVIEW.value
    return target in ALLOWED_TRANSITIONS.get(current, set())


def _work_address_for(job: Job | None, arrangement: str | None) -> str | None:
    """Only hybrid/on-site roles carry an address; remote roles record "Remote"."""
    if arrangement == WorkArrangement.REMOTE.value:
        return None
    if job is None:
        return None
    parts = [job.street_address, job.city, job.region, job.postal_code]
    return ", ".join(part for part in parts if part) or None


def record_event(
    db: Session,
    application: Application,
    *,
    from_status: str | None,
    to_status: str,
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application.id,
        from_status=from_status,
        to_status=to_status,
        note=note,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def create_application(
    db: Session,
    user: User,
    *,
    job: Job | None = None,
    resume: Resume | None = None,
    contact_id: uuid.UUID | None = None,
    company_name: str | None = None,
    position_title: str | None = None,
    location: str | None = None,
    work_arrangement: str | None = None,
    work_address: str | None = None,
    application_url: str | None = None,
    status: str = ApplicationStatus.APPLIED.value,
    applied_at: date | None = None,
    notes: str | None = None,
    match_score: int | None = None,
) -> Application:
    """Create a tracked application, snapshotting everything it needs to stand alone."""
    if job is None and not (company_name and position_title):
        raise ValueError("A manual application needs both a company name and a position title")

    arrangement = work_arrangement or (job.work_arrangement if job else None)
    application = Application(
        user_id=user.id,
        job_id=job.id if job else None,
        resume_id=resume.id if resume else None,
        contact_id=contact_id,
        company_name=company_name or (job.company.name if job and job.company else "Unknown"),
        position_title=position_title or (job.title if job else "Unknown"),
        location=location or (job.location if job else None),
        work_arrangement=arrangement,
        work_address=work_address or _work_address_for(job, arrangement),
        application_url=application_url or (job.apply_url or job.source_url if job else None),
        job_description_snapshot=(
            job.description_snapshot or job.description if job else None
        ),
        salary_min=job.salary_min if job else None,
        salary_max=job.salary_max if job else None,
        status=status,
        applied_at=applied_at
        or (date.today() if status == ApplicationStatus.APPLIED.value else None),
        match_score=match_score,
        notes=notes,
    )
    db.add(application)
    db.flush()
    record_event(db, application, from_status=None, to_status=status, note="Application created")
    return application


def change_status(
    db: Session,
    application: Application,
    *,
    status: str,
    note: str | None = None,
    occurred_at: datetime | None = None,
) -> Application:
    current = application.status
    if not can_transition(current, status):
        raise TransitionError(f"Cannot move an application from {current} to {status}")

    now = occurred_at or datetime.now(timezone.utc)
    application.status = status
    if status == ApplicationStatus.APPLIED.value and application.applied_at is None:
        application.applied_at = now.date()
    if status in RESPONSE_STATUSES and application.first_response_at is None:
        application.first_response_at = now
    if status in {
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
        ApplicationStatus.CLOSED.value,
    }:
        application.closed_at = now
    elif status == ApplicationStatus.TODO.value:
        application.closed_at = None

    record_event(db, application, from_status=current, to_status=status, note=note, occurred_at=now)
    db.flush()
    return application


def application_for_recommendation(
    db: Session, user: User, recommendation: Recommendation
) -> Application | None:
    stmt = select(Application).where(
        Application.user_id == user.id, Application.job_id == recommendation.job_id
    )
    return db.execute(stmt).scalars().first()


def _count_by_status(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(Application.status, func.count())
        .where(Application.user_id == user_id)
        .group_by(Application.status)
    ).all()
    return {status: count for status, count in rows}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100 * numerator / denominator, 1)


def dashboard_stats(db: Session, user: User) -> DashboardStats:
    """Aggregate counts and rates for the dashboard (feature 13)."""
    counts = _count_by_status(db, user.id)
    total = sum(counts.values())

    interviews = counts.get(ApplicationStatus.INTERVIEW.value, 0)
    offers = counts.get(ApplicationStatus.OFFER.value, 0)
    rejections = counts.get(ApplicationStatus.REJECTED.value, 0)

    # An application that reached interview/offer/rejection got a response, and
    # so did anything already carrying a first-response timestamp.
    responded = db.execute(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user.id, Application.first_response_at.is_not(None))
    ).scalar_one()
    responses = max(responded, interviews + offers + rejections)

    submitted = db.execute(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user.id, Application.applied_at.is_not(None))
    ).scalar_one()

    now = datetime.now(timezone.utc).date()
    last_7 = db.execute(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user.id, Application.applied_at >= now - timedelta(days=7))
    ).scalar_one()
    last_30 = db.execute(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user.id, Application.applied_at >= now - timedelta(days=30))
    ).scalar_one()

    skipped_recommendations = db.execute(
        select(func.count())
        .select_from(Recommendation)
        .where(
            Recommendation.user_id == user.id,
            Recommendation.status == RecommendationStatus.SKIPPED.value,
        )
    ).scalar_one()

    active_batch = db.execute(
        select(Batch)
        .where(Batch.user_id == user.id, Batch.status == BatchStatus.ACTIVE.value)
        .order_by(Batch.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    remaining = 0
    if active_batch is not None:
        live = active_batch.live_recommendations
        remaining = sum(1 for rec in live if not rec.is_resolved)

    return DashboardStats(
        total_applications=total,
        applied=counts.get(ApplicationStatus.APPLIED.value, 0),
        responses=responses,
        interviews=interviews,
        offers=offers,
        rejections=rejections,
        withdrawn=counts.get(ApplicationStatus.WITHDRAWN.value, 0),
        closed=counts.get(ApplicationStatus.CLOSED.value, 0),
        skipped=counts.get(ApplicationStatus.SKIPPED.value, 0),
        todo=counts.get(ApplicationStatus.TODO.value, 0),
        in_pipeline=sum(
            count for status, count in counts.items() if status in OPEN_PIPELINE_STATUSES
        ),
        response_rate=_rate(responses, submitted),
        interview_rate=_rate(interviews + offers, submitted),
        offer_rate=_rate(offers, submitted),
        pipeline_by_status=[
            StatusCount(status=status.value, count=counts.get(status.value, 0))
            for status in ApplicationStatus
        ],
        applications_last_7_days=last_7,
        applications_last_30_days=last_30,
        jobs_skipped=skipped_recommendations,
        active_batch_remaining=remaining,
    )
