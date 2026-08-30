"""Admin moderation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import BlacklistScope
from app.schemas.common import ORMModel


class BlacklistRead(ORMModel):
    id: uuid.UUID
    scope: str
    value: str
    reason: str | None = None
    created_at: datetime


class BlacklistCreate(BaseModel):
    scope: BlacklistScope
    value: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)


class AdminJobRow(BaseModel):
    id: uuid.UUID
    title: str
    company_name: str
    company_slug: str
    company_domain: str | None = None
    location: str | None = None
    status: str
    source_type: str | None = None
    source_url: str
    date_posted: str | None = None
    last_verified_at: datetime | None = None
    verification_failures: int
    duplicate_of_id: uuid.UUID | None = None
    recommendation_count: int
    moderation_notes: str | None = None


class AdminJobAction(BaseModel):
    """Bulk moderation action applied to a set of jobs."""

    job_ids: list[uuid.UUID] = Field(min_length=1)
    action: str = Field(
        description="One of: disable, enable, mark_stale, mark_duplicate, mark_scam, mark_closed"
    )
    duplicate_of_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)


class AdminActionResult(BaseModel):
    updated: int
    action: str


class AdminStats(BaseModel):
    total_jobs: int
    active_jobs: int
    closed_jobs: int
    stale_jobs: int
    duplicate_jobs: int
    disabled_jobs: int
    scam_jobs: int
    total_companies: int
    blacklisted_companies: int
    total_sources: int
    enabled_sources: int
    total_users: int
