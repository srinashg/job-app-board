"""Admin moderation: inspect jobs, disable/flag them, manage blacklists."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import AdminUser, DbSession, PageParams
from app.models.enums import BlacklistScope, JobStatus, SourceType
from app.models.job import Blacklist, Company, Job, JobSource
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.admin import (
    AdminActionResult,
    AdminJobAction,
    AdminJobRow,
    AdminStats,
    BlacklistCreate,
    BlacklistRead,
)
from app.schemas.common import Message, Page
from app.schemas.job import (
    FreshnessRunRequest,
    FreshnessRunResult,
    IngestRunRequest,
    IngestRunResult,
    JobSourceCreate,
    JobSourceRead,
    JobSourceUpdate,
)
from app.services.freshness import close_recommendations_for_job, run_freshness_check
from app.services.ingestion import get_or_create_company, run_ingestion, seed_default_sources
from app.services.text import normalize_domain, slugify

router = APIRouter(prefix="/admin", tags=["admin"])

#: Moderation actions and the job status each one sets.
ACTION_STATUS = {
    "disable": JobStatus.DISABLED.value,
    "enable": JobStatus.ACTIVE.value,
    "mark_stale": JobStatus.STALE.value,
    "mark_duplicate": JobStatus.DUPLICATE.value,
    "mark_scam": JobStatus.SCAM.value,
    "mark_closed": JobStatus.CLOSED.value,
}

#: Actions after which a job must stop being recommended to anyone.
WITHDRAWING_ACTIONS = {"disable", "mark_stale", "mark_duplicate", "mark_scam", "mark_closed"}


@router.get("/jobs", response_model=Page[AdminJobRow])
def list_jobs(
    admin: AdminUser,
    db: DbSession,
    page: PageParams,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    company: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[AdminJobRow]:
    """The `/admin/jobs` table: every listing with its moderation state."""
    conditions = []
    if status_filter:
        conditions.append(Job.status == status_filter.value)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Job.title).like(pattern),
                func.lower(Job.source_url).like(pattern),
                func.lower(Company.name).like(pattern),
            )
        )
    if company:
        conditions.append(func.lower(Company.name).like(f"%{company.lower()}%"))

    total = db.execute(
        select(func.count())
        .select_from(Job)
        .join(Company, Job.company_id == Company.id)
        .where(*conditions)
    ).scalar_one()

    rows = list(
        db.execute(
            select(Job)
            .join(Company, Job.company_id == Company.id)
            .where(*conditions)
            .options(selectinload(Job.company), selectinload(Job.source))
            .order_by(Job.first_seen_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )

    counts = dict(
        db.execute(
            select(Recommendation.job_id, func.count())
            .where(Recommendation.job_id.in_([job.id for job in rows] or [uuid.uuid4()]))
            .group_by(Recommendation.job_id)
        ).all()
    )

    return Page[AdminJobRow](
        items=[
            AdminJobRow(
                id=job.id,
                title=job.title,
                company_name=job.company.name,
                company_slug=job.company.slug,
                company_domain=job.company.domain,
                location=job.location,
                status=job.status,
                source_type=job.source.source_type if job.source else None,
                source_url=job.source_url,
                date_posted=job.date_posted.isoformat() if job.date_posted else None,
                last_verified_at=job.last_verified_at,
                verification_failures=job.verification_failures,
                duplicate_of_id=job.duplicate_of_id,
                recommendation_count=counts.get(job.id, 0),
                moderation_notes=job.moderation_notes,
            )
            for job in rows
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/jobs/actions", response_model=AdminActionResult)
def moderate_jobs(payload: AdminJobAction, admin: AdminUser, db: DbSession) -> AdminActionResult:
    """Apply one moderation action to a set of jobs."""
    if payload.action not in ACTION_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action. Use one of: {', '.join(sorted(ACTION_STATUS))}",
        )
    if payload.action == "mark_duplicate" and payload.duplicate_of_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mark_duplicate needs the id of the job being duplicated",
        )

    jobs = list(db.execute(select(Job).where(Job.id.in_(payload.job_ids))).scalars())
    if not jobs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching jobs")

    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = ACTION_STATUS[payload.action]
        if payload.action == "mark_duplicate":
            if payload.duplicate_of_id == job.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A job cannot be a duplicate of itself",
                )
            job.duplicate_of_id = payload.duplicate_of_id
        if payload.action == "enable":
            job.duplicate_of_id = None
            job.closed_at = None
            job.verification_failures = 0
        if payload.action == "mark_closed":
            job.closed_at = now
        if payload.notes:
            job.moderation_notes = payload.notes
        if payload.action in WITHDRAWING_ACTIONS:
            close_recommendations_for_job(db, job)

    db.flush()
    return AdminActionResult(updated=len(jobs), action=payload.action)


@router.get("/blacklists", response_model=list[BlacklistRead])
def list_blacklists(admin: AdminUser, db: DbSession) -> list[Blacklist]:
    return list(db.execute(select(Blacklist).order_by(Blacklist.created_at.desc())).scalars())


@router.post("/blacklists", response_model=BlacklistRead, status_code=status.HTTP_201_CREATED)
def add_blacklist(payload: BlacklistCreate, admin: AdminUser, db: DbSession) -> Blacklist:
    """Blacklist a company, a domain or a single job, and withdraw its listings."""
    value = payload.value.strip()
    if payload.scope == BlacklistScope.DOMAIN:
        value = normalize_domain(value) or value
    elif payload.scope == BlacklistScope.COMPANY:
        value = slugify(value)

    existing = db.execute(
        select(Blacklist).where(
            Blacklist.scope == payload.scope.value, Blacklist.value == value
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That entry is already blacklisted"
        )

    entry = Blacklist(
        scope=payload.scope.value,
        value=value,
        reason=payload.reason,
        created_by_id=admin.id,
    )
    db.add(entry)
    db.flush()
    _enforce_blacklist(db, entry)
    return entry


def _enforce_blacklist(db: DbSession, entry: Blacklist) -> None:
    """Disable everything the new blacklist entry covers."""
    if entry.scope == BlacklistScope.JOB.value:
        try:
            job_id = uuid.UUID(entry.value)
        except ValueError:
            return
        job = db.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.DISABLED.value
            close_recommendations_for_job(db, job)
        return

    if entry.scope == BlacklistScope.COMPANY.value:
        companies = list(db.execute(select(Company).where(Company.slug == entry.value)).scalars())
    else:
        companies = list(db.execute(select(Company).where(Company.domain == entry.value)).scalars())

    for company in companies:
        company.is_blacklisted = True
        for job in company.jobs:
            job.status = JobStatus.DISABLED.value
            close_recommendations_for_job(db, job)
    db.flush()


@router.delete("/blacklists/{entry_id}", response_model=Message)
def remove_blacklist(entry_id: uuid.UUID, admin: AdminUser, db: DbSession) -> Message:
    entry = db.get(Blacklist, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    if entry.scope == BlacklistScope.COMPANY.value:
        for company in db.execute(select(Company).where(Company.slug == entry.value)).scalars():
            company.is_blacklisted = False
    elif entry.scope == BlacklistScope.DOMAIN.value:
        for company in db.execute(select(Company).where(Company.domain == entry.value)).scalars():
            company.is_blacklisted = False
    db.execute(delete(Blacklist).where(Blacklist.id == entry.id))
    db.flush()
    return Message(detail="Blacklist entry removed. Jobs stay disabled until re-enabled.")


@router.get("/sources", response_model=list[JobSourceRead])
def list_sources(admin: AdminUser, db: DbSession) -> list[JobSource]:
    return list(db.execute(select(JobSource).order_by(JobSource.name)).scalars())


@router.post("/sources", response_model=JobSourceRead, status_code=status.HTTP_201_CREATED)
def add_source(payload: JobSourceCreate, admin: AdminUser, db: DbSession) -> JobSource:
    existing = db.execute(
        select(JobSource).where(
            JobSource.source_type == payload.source_type.value,
            JobSource.external_slug == payload.external_slug,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That source is already registered"
        )
    company = get_or_create_company(
        db, payload.company_name or payload.name, payload.company_domain
    )
    source = JobSource(
        company_id=company.id,
        name=payload.name,
        source_type=payload.source_type.value,
        external_slug=payload.external_slug,
        base_url=payload.base_url,
    )
    db.add(source)
    db.flush()
    return source


@router.patch("/sources/{source_id}", response_model=JobSourceRead)
def update_source(
    source_id: uuid.UUID, payload: JobSourceUpdate, admin: AdminUser, db: DbSession
) -> JobSource:
    source = db.get(JobSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.flush()
    return source


@router.post("/sources/seed", response_model=Message)
def seed_sources(admin: AdminUser, db: DbSession) -> Message:
    added = seed_default_sources(db)
    return Message(detail=f"Registered {added} new source(s)")


@router.post("/ingest", response_model=IngestRunResult)
def trigger_ingest(payload: IngestRunRequest, admin: AdminUser, db: DbSession) -> IngestRunResult:
    """Fetch listings from the registered career-site/ATS sources."""
    stats = run_ingestion(
        db, source_ids=payload.source_ids, limit_per_source=payload.limit_per_source
    )
    return IngestRunResult(
        sources_run=stats.sources_run,
        jobs_fetched=stats.jobs_fetched,
        jobs_created=stats.jobs_created,
        jobs_updated=stats.jobs_updated,
        duplicates_detected=stats.duplicates_detected,
        errors=stats.errors,
    )


@router.post("/freshness", response_model=FreshnessRunResult)
def trigger_freshness(
    payload: FreshnessRunRequest, admin: AdminUser, db: DbSession
) -> FreshnessRunResult:
    """Re-verify listings and close the ones that are gone."""
    stats = run_freshness_check(db, limit=payload.limit, force=payload.force)
    return FreshnessRunResult(
        checked=stats.checked,
        still_open=stats.still_open,
        marked_closed=stats.marked_closed,
        marked_stale=stats.marked_stale,
        errors=stats.errors,
    )


@router.get("/stats", response_model=AdminStats)
def read_stats(admin: AdminUser, db: DbSession) -> AdminStats:
    status_counts = dict(
        db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    return AdminStats(
        total_jobs=sum(status_counts.values()),
        active_jobs=status_counts.get(JobStatus.ACTIVE.value, 0),
        closed_jobs=status_counts.get(JobStatus.CLOSED.value, 0),
        stale_jobs=status_counts.get(JobStatus.STALE.value, 0),
        duplicate_jobs=status_counts.get(JobStatus.DUPLICATE.value, 0),
        disabled_jobs=status_counts.get(JobStatus.DISABLED.value, 0),
        scam_jobs=status_counts.get(JobStatus.SCAM.value, 0),
        total_companies=db.execute(select(func.count()).select_from(Company)).scalar_one(),
        blacklisted_companies=db.execute(
            select(func.count()).select_from(Company).where(Company.is_blacklisted.is_(True))
        ).scalar_one(),
        total_sources=db.execute(select(func.count()).select_from(JobSource)).scalar_one(),
        enabled_sources=db.execute(
            select(func.count()).select_from(JobSource).where(JobSource.is_enabled.is_(True))
        ).scalar_one(),
        total_users=db.execute(select(func.count()).select_from(User)).scalar_one(),
    )
