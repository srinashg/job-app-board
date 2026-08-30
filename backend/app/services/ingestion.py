"""Persist jobs fetched from sources, with dedupe and blacklist enforcement."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import BlacklistScope, JobStatus, SourceType
from app.models.job import Blacklist, Company, Job, JobSource
from app.services.dedupe import compute_fingerprint, find_duplicate
from app.services.ingest import RawJob, get_client
from app.services.ingest.base import (
    infer_experience_level,
    parse_citizenship_required,
    parse_clearance,
    parse_min_years,
    parse_salary,
    parse_sponsorship,
)
from app.services.ingest.http import HttpFetcher
from app.services.taxonomy import extract_technologies
from app.services.text import normalize_domain, slugify

logger = logging.getLogger(__name__)

#: Description phrases that mark a "required" vs a "nice to have" skills block.
REQUIRED_SECTION_MARKERS = (
    "requirements",
    "required",
    "qualifications",
    "must have",
    "what you'll need",
    "what you need",
    "who you are",
)
PREFERRED_SECTION_MARKERS = (
    "preferred",
    "nice to have",
    "bonus",
    "plus",
    "desirable",
)


@dataclass
class IngestStats:
    sources_run: int = 0
    jobs_fetched: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    duplicates_detected: int = 0
    errors: list[str] = field(default_factory=list)


def _split_skill_sections(description: str) -> tuple[list[str], list[str]]:
    """Split extracted technologies into required vs preferred by section."""
    lowered = description.lower()
    required_at = min(
        (lowered.find(marker) for marker in REQUIRED_SECTION_MARKERS if marker in lowered),
        default=-1,
    )
    preferred_at = min(
        (lowered.find(marker) for marker in PREFERRED_SECTION_MARKERS if marker in lowered),
        default=-1,
    )
    if required_at == -1 and preferred_at == -1:
        return extract_technologies(description), []
    if preferred_at == -1:
        return extract_technologies(description[required_at:]), []
    if required_at == -1 or preferred_at < required_at:
        preferred = extract_technologies(description[preferred_at:])
        required = [
            tech for tech in extract_technologies(description) if tech not in set(preferred)
        ]
        return required, preferred
    required = extract_technologies(description[required_at:preferred_at])
    preferred = [
        tech
        for tech in extract_technologies(description[preferred_at:])
        if tech not in set(required)
    ]
    return required, preferred


def is_blacklisted(db: Session, *, company_slug: str | None, domain: str | None) -> bool:
    values = [value for value in (company_slug, domain) if value]
    if not values:
        return False
    stmt = select(Blacklist).where(
        Blacklist.scope.in_([BlacklistScope.COMPANY.value, BlacklistScope.DOMAIN.value]),
        Blacklist.value.in_(values),
    )
    return db.execute(stmt).first() is not None


def get_or_create_company(
    db: Session, name: str, domain: str | None = None, careers_url: str | None = None
) -> Company:
    slug = slugify(name)
    company = db.execute(select(Company).where(Company.slug == slug)).scalar_one_or_none()
    if company is None:
        company = Company(
            name=name.strip() or slug,
            slug=slug,
            domain=normalize_domain(domain),
            careers_url=careers_url,
        )
        db.add(company)
        db.flush()
    elif domain and not company.domain:
        company.domain = normalize_domain(domain)
    return company


def _apply_raw_job(job: Job, raw: RawJob, *, is_new: bool) -> None:
    """Copy a fetched posting onto a Job row, deriving the parsed fields."""
    description = raw.description or ""
    required, preferred = _split_skill_sections(description)
    salary_min, salary_max = raw.salary_min, raw.salary_max
    if salary_min is None and salary_max is None:
        salary_min, salary_max = parse_salary(description)

    job.title = raw.title
    job.description = description
    if is_new or not job.description_snapshot:
        # The snapshot is what applications quote, so it is written once.
        job.description_snapshot = description
    job.location = raw.location
    job.city = raw.city
    job.region = raw.region
    job.country = raw.country
    job.postal_code = raw.postal_code
    job.street_address = raw.street_address
    job.latitude = raw.latitude
    job.longitude = raw.longitude
    job.work_arrangement = raw.work_arrangement
    job.salary_min = salary_min
    job.salary_max = salary_max
    job.salary_currency = raw.salary_currency or ("USD" if salary_min or salary_max else None)
    job.salary_period = raw.salary_period or ("year" if salary_min or salary_max else None)
    job.experience_level = infer_experience_level(raw.title, description)
    job.min_years_experience = parse_min_years(description)
    job.technologies = extract_technologies(description)
    job.required_skills = required
    job.preferred_skills = preferred
    job.requires_clearance = parse_clearance(description)
    job.sponsorship_available = parse_sponsorship(description)
    job.citizenship_required = parse_citizenship_required(description)
    job.date_posted = raw.date_posted
    job.source_url = raw.source_url
    job.apply_url = raw.apply_url or raw.source_url
    job.raw_payload = raw.raw_payload


def upsert_job(db: Session, source: JobSource | None, raw: RawJob) -> tuple[Job | None, str]:
    """Insert or refresh one fetched posting.

    Returns the job and one of ``created``/``updated``/``duplicate``/``skipped``.
    """
    if not raw.title or not raw.source_url:
        return None, "skipped"

    company_domain = raw.company_domain or normalize_domain(raw.source_url)
    company_slug = slugify(raw.company_name)
    if is_blacklisted(db, company_slug=company_slug, domain=company_domain):
        return None, "skipped"

    company = get_or_create_company(db, raw.company_name, company_domain)
    if company.is_blacklisted:
        return None, "skipped"

    now = datetime.now(timezone.utc)
    existing: Job | None = None
    if source is not None and raw.external_id:
        existing = db.execute(
            select(Job).where(
                Job.source_id == source.id, Job.external_id == str(raw.external_id)
            )
        ).scalar_one_or_none()

    fingerprint = compute_fingerprint(company.slug, raw.title, raw.location)

    if existing is not None:
        _apply_raw_job(existing, raw, is_new=False)
        existing.fingerprint = fingerprint
        existing.last_verified_at = now
        existing.last_checked_at = now
        existing.verification_failures = 0
        if existing.status in (JobStatus.CLOSED.value, JobStatus.STALE.value):
            # The source is listing it again, so it is open again.
            existing.status = JobStatus.ACTIVE.value
            existing.closed_at = None
        return existing, "updated"

    duplicate = find_duplicate(
        db,
        company_id=company.id,
        fingerprint=fingerprint,
        title=raw.title,
        description=raw.description or "",
    )

    job = Job(
        company_id=company.id,
        source_id=source.id if source is not None else None,
        external_id=str(raw.external_id) if raw.external_id else None,
        fingerprint=fingerprint,
        first_seen_at=now,
        last_verified_at=now,
        last_checked_at=now,
        status=JobStatus.ACTIVE.value,
        source_url=raw.source_url,
        description="",
    )
    _apply_raw_job(job, raw, is_new=True)
    outcome = "created"
    if duplicate is not None:
        job.status = JobStatus.DUPLICATE.value
        job.duplicate_of_id = duplicate.job.id
        job.moderation_notes = (
            f"Auto-marked duplicate of {duplicate.job.id} "
            f"({duplicate.reason}, similarity {duplicate.similarity:.2f})"
        )
        outcome = "duplicate"
    db.add(job)
    db.flush()
    return job, outcome


def run_source(
    db: Session,
    source: JobSource,
    *,
    limit: int = 100,
    fetcher: HttpFetcher | None = None,
) -> IngestStats:
    """Fetch one source and persist everything it returns."""
    stats = IngestStats(sources_run=1)
    try:
        client = get_client(source.source_type, fetcher=fetcher)
        raw_jobs = client.fetch(source.external_slug, limit=limit)
    except Exception as exc:
        message = f"{source.name}: {exc}"
        logger.warning("Source fetch failed: %s", message)
        stats.errors.append(message)
        source.last_fetch_status = "error"
        source.last_fetch_error = str(exc)[:2000]
        source.last_fetched_at = datetime.now(timezone.utc)
        db.flush()
        return stats

    for raw in raw_jobs:
        stats.jobs_fetched += 1
        if source.company is not None and not raw.company_name.strip():
            raw.company_name = source.company.name
        try:
            _, outcome = upsert_job(db, source, raw)
        except Exception as exc:  # one bad posting must not kill the run
            logger.exception("Failed to persist posting %s", raw.external_id)
            stats.errors.append(f"{source.name}/{raw.external_id}: {exc}")
            continue
        if outcome == "created":
            stats.jobs_created += 1
        elif outcome == "updated":
            stats.jobs_updated += 1
        elif outcome == "duplicate":
            stats.duplicates_detected += 1

    source.last_fetched_at = datetime.now(timezone.utc)
    source.last_fetch_status = "ok"
    source.last_fetch_error = None
    source.jobs_seen = (source.jobs_seen or 0) + stats.jobs_fetched
    db.flush()
    return stats


def run_ingestion(
    db: Session,
    *,
    source_ids: list[uuid.UUID] | None = None,
    limit_per_source: int = 100,
    fetcher: HttpFetcher | None = None,
) -> IngestStats:
    """Run every enabled source (or the given subset)."""
    stmt = select(JobSource).where(JobSource.is_enabled.is_(True))
    if source_ids:
        stmt = stmt.where(JobSource.id.in_(source_ids))
    sources = list(db.execute(stmt).scalars())

    total = IngestStats()
    for source in sources:
        stats = run_source(db, source, limit=limit_per_source, fetcher=fetcher)
        total.sources_run += stats.sources_run
        total.jobs_fetched += stats.jobs_fetched
        total.jobs_created += stats.jobs_created
        total.jobs_updated += stats.jobs_updated
        total.duplicates_detected += stats.duplicates_detected
        total.errors.extend(stats.errors)
    db.flush()
    return total


def seed_default_sources(db: Session) -> int:
    """Register a starter set of public ATS boards. Returns how many were added."""
    defaults = [
        ("Stripe", SourceType.GREENHOUSE.value, "stripe", "stripe.com"),
        ("Airbnb", SourceType.GREENHOUSE.value, "airbnb", "airbnb.com"),
        ("Databricks", SourceType.GREENHOUSE.value, "databricks", "databricks.com"),
        ("Netflix", SourceType.LEVER.value, "netflix", "netflix.com"),
        ("Ramp", SourceType.ASHBY.value, "ramp", "ramp.com"),
        ("Linear", SourceType.ASHBY.value, "linear", "linear.app"),
    ]
    added = 0
    for name, source_type, slug, domain in defaults:
        exists = db.execute(
            select(JobSource).where(
                JobSource.source_type == source_type, JobSource.external_slug == slug
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue
        company = get_or_create_company(db, name, domain)
        db.add(
            JobSource(
                company_id=company.id,
                name=name,
                source_type=source_type,
                external_slug=slug,
            )
        )
        added += 1
    db.flush()
    return added
