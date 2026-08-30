"""Batch and recommendation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SkipReason
from app.schemas.common import ORMModel
from app.schemas.job import JobSummary
from app.schemas.matching import MatchResult


class RecommendationRead(ORMModel):
    id: uuid.UUID
    job_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    position: int
    status: str
    match_score: int
    skip_reason: str | None = None
    skip_note: str | None = None
    resolved_at: datetime | None = None
    job: JobSummary
    match_explanation: MatchResult | None = None


class BatchRead(ORMModel):
    id: uuid.UUID
    sequence: int
    size: int
    status: str
    completed_at: datetime | None = None
    created_at: datetime
    recommendations: list[RecommendationRead]
    resolved_count: int
    is_complete: bool


class BatchState(BaseModel):
    """What the batch screen needs in a single call."""

    batch: BatchRead | None = None
    can_unlock_next: bool
    remaining: int
    #: Set when we could not fill a batch: no eligible jobs left right now.
    exhausted: bool = False
    message: str | None = None


class SkipRequest(BaseModel):
    reason: SkipReason
    note: str | None = Field(default=None, max_length=1000)


class ApplyRequest(BaseModel):
    resume_id: uuid.UUID | None = None
    application_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=4000)
