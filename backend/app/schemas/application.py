"""Application tracker schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import ApplicationStatus, WorkArrangement
from app.schemas.common import ORMModel


class ContactRead(ORMModel):
    id: uuid.UUID
    name: str
    title: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None


class ContactWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    company_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    linkedin_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationEventRead(ORMModel):
    id: uuid.UUID
    from_status: str | None = None
    to_status: str
    note: str | None = None
    occurred_at: datetime


class ApplicationRead(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID | None = None
    resume_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_name: str
    position_title: str
    location: str | None = None
    work_arrangement: str | None = None
    work_address: str | None = None
    application_url: str | None = None
    status: str
    applied_at: date | None = None
    first_response_at: datetime | None = None
    closed_at: datetime | None = None
    match_score: int | None = None
    notes: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationRead):
    job_description_snapshot: str | None = None
    events: list[ApplicationEventRead] = Field(default_factory=list)
    contact: ContactRead | None = None


class ApplicationCreate(BaseModel):
    """Log an application, either from a tracked job or entered by hand."""

    job_id: uuid.UUID | None = None
    resume_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_name: str | None = Field(default=None, max_length=255)
    position_title: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=255)
    work_arrangement: WorkArrangement | None = None
    work_address: str | None = Field(default=None, max_length=400)
    application_url: str | None = Field(default=None, max_length=1000)
    status: ApplicationStatus = ApplicationStatus.APPLIED
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationUpdate(BaseModel):
    resume_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    company_name: str | None = Field(default=None, max_length=255)
    position_title: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=255)
    work_arrangement: WorkArrangement | None = None
    work_address: str | None = Field(default=None, max_length=400)
    application_url: str | None = Field(default=None, max_length=1000)
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=1000)
    occurred_at: datetime | None = None


class StatusCount(BaseModel):
    status: str
    count: int


class DashboardStats(BaseModel):
    total_applications: int
    applied: int
    responses: int
    interviews: int
    offers: int
    rejections: int
    withdrawn: int
    closed: int
    skipped: int
    todo: int
    in_pipeline: int
    response_rate: float = Field(ge=0, le=100)
    interview_rate: float = Field(ge=0, le=100)
    offer_rate: float = Field(ge=0, le=100)
    pipeline_by_status: list[StatusCount] = Field(default_factory=list)
    applications_last_7_days: int
    applications_last_30_days: int
    jobs_skipped: int
    active_batch_remaining: int
