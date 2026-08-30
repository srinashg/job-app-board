"""Job, company, source and ingestion schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import JobStatus, SourceType
from app.schemas.common import ORMModel


class CompanyRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    website: str | None = None
    domain: str | None = None
    careers_url: str | None = None
    industry: str | None = None
    size: str | None = None
    headquarters: str | None = None
    description: str | None = None
    is_blacklisted: bool


class JobSummary(ORMModel):
    id: uuid.UUID
    title: str
    location: str | None = None
    work_arrangement: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    experience_level: str | None = None
    technologies: list[str]
    date_posted: date | None = None
    source_url: str
    status: str
    last_verified_at: datetime | None = None
    company: CompanyRead


class JobDetail(JobSummary):
    description: str
    description_snapshot: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None
    street_address: str | None = None
    min_years_experience: float | None = None
    required_skills: list[str]
    preferred_skills: list[str]
    industry: str | None = None
    requires_clearance: str | None = None
    sponsorship_available: bool | None = None
    citizenship_required: bool
    apply_url: str | None = None
    first_seen_at: datetime
    last_checked_at: datetime | None = None
    duplicate_of_id: uuid.UUID | None = None


class JobSourceRead(ORMModel):
    id: uuid.UUID
    name: str
    source_type: str
    external_slug: str
    base_url: str | None = None
    is_enabled: bool
    last_fetched_at: datetime | None = None
    last_fetch_status: str | None = None
    last_fetch_error: str | None = None
    jobs_seen: int


class JobSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: SourceType
    external_slug: str = Field(min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=500)
    company_name: str | None = Field(default=None, max_length=255)
    company_domain: str | None = Field(default=None, max_length=255)


class JobSourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None
    base_url: str | None = Field(default=None, max_length=500)


class IngestRunRequest(BaseModel):
    source_ids: list[uuid.UUID] | None = None
    limit_per_source: int = Field(default=100, ge=1, le=1000)


class IngestRunResult(BaseModel):
    sources_run: int
    jobs_fetched: int
    jobs_created: int
    jobs_updated: int
    duplicates_detected: int
    errors: list[str] = Field(default_factory=list)


class FreshnessRunRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    #: Re-check even listings whose recheck interval has not elapsed yet.
    force: bool = False


class FreshnessRunResult(BaseModel):
    checked: int
    still_open: int
    marked_closed: int
    marked_stale: int
    errors: list[str] = Field(default_factory=list)


class JobAdminUpdate(BaseModel):
    status: JobStatus | None = None
    duplicate_of_id: uuid.UUID | None = None
    moderation_notes: str | None = None
