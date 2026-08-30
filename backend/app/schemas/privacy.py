"""Privacy and account-control schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AccountDeleteRequest(BaseModel):
    """Deleting an account is irreversible, so require an explicit confirmation."""

    password: str | None = None
    confirmation: str = Field(description='Must be the literal string "DELETE".')
    reason: str | None = Field(default=None, max_length=1000)


class DataExport(BaseModel):
    generated_at: datetime
    user: dict[str, Any]
    profile: dict[str, Any] | None = None
    eligibility: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    consents: list[dict[str, Any]] = Field(default_factory=list)
    resumes: list[dict[str, Any]] = Field(default_factory=list)
    applications: list[dict[str, Any]] = Field(default_factory=list)
    contacts: list[dict[str, Any]] = Field(default_factory=list)


class PrivacySummary(BaseModel):
    resume_count: int
    stored_resume_files: int
    application_count: int
    contact_count: int
    consents: list[dict[str, Any]] = Field(default_factory=list)
    deletion_requested_at: datetime | None = None
