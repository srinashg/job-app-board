"""Job browsing and the job-details page."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession, PageParams
from app.models.enums import JobStatus, RecommendationStatus, WorkArrangement
from app.models.job import Company, Job
from app.models.recommendation import Recommendation
from app.schemas.common import Page
from app.schemas.job import JobDetail, JobSummary
from app.schemas.matching import MatchResult
from app.services.matching import score_job
from app.services.recommendations import build_candidate_profile

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobDetailResponse(BaseModel):
    """Everything the job-details page renders in one call."""

    job: JobDetail
    match: MatchResult | None = None
    recommendation_id: uuid.UUID | None = None
    recommendation_status: str | None = None
    is_saved: bool = False
    already_applied: bool = False


@router.get("", response_model=Page[JobSummary])
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    page: PageParams,
    q: Annotated[str | None, Query(max_length=200)] = None,
    company: Annotated[str | None, Query(max_length=200)] = None,
    work_arrangement: WorkArrangement | None = None,
    min_salary: Annotated[int | None, Query(ge=0)] = None,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
) -> Page[JobSummary]:
    """Browse the job pool. Defaults to open, non-duplicate listings."""
    conditions = [Job.duplicate_of_id.is_(None)]
    conditions.append(
        Job.status == (status_filter.value if status_filter else JobStatus.ACTIVE.value)
    )
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            or_(func.lower(Job.title).like(pattern), func.lower(Job.description).like(pattern))
        )
    if company:
        conditions.append(func.lower(Company.name).like(f"%{company.lower()}%"))
    if work_arrangement:
        conditions.append(Job.work_arrangement == work_arrangement.value)
    if min_salary is not None:
        conditions.append(Job.salary_max >= min_salary)

    base = select(Job).join(Company, Job.company_id == Company.id).where(*conditions)
    total = db.execute(
        select(func.count()).select_from(
            select(Job.id).join(Company, Job.company_id == Company.id).where(*conditions).subquery()
        )
    ).scalar_one()
    rows = list(
        db.execute(
            base.options(selectinload(Job.company))
            .order_by(Job.date_posted.desc().nullslast(), Job.first_seen_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return Page[JobSummary](
        items=[JobSummary.model_validate(job) for job in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
def read_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobDetailResponse:
    """Job details with the match explanation for the signed-in user."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    recommendation = db.execute(
        select(Recommendation).where(
            Recommendation.user_id == user.id, Recommendation.job_id == job.id
        )
    ).scalar_one_or_none()

    if recommendation is not None and recommendation.match_explanation:
        # Reuse the explanation the batch was built from, so what the user saw
        # on the card is what the details page repeats.
        match = MatchResult.model_validate(recommendation.match_explanation)
    else:
        match = score_job(job, build_candidate_profile(db, user))

    from app.models.application import Application

    already_applied = (
        db.execute(
            select(Application.id)
            .where(Application.user_id == user.id, Application.job_id == job.id)
            .limit(1)
        ).first()
        is not None
    )

    return JobDetailResponse(
        job=JobDetail.model_validate(job),
        match=match,
        recommendation_id=recommendation.id if recommendation else None,
        recommendation_status=recommendation.status if recommendation else None,
        is_saved=(
            recommendation is not None
            and recommendation.status == RecommendationStatus.SAVED.value
        ),
        already_applied=already_applied,
    )
