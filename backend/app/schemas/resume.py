"""Resume upload, parsing and version-manager schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExperienceEntry(BaseModel):
    company: str | None = None
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    description: str | None = None
    is_current: bool = False


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None


class CertificationEntry(BaseModel):
    name: str
    issuer: str | None = None
    issued_date: str | None = None
    expires_date: str | None = None
    credential_id: str | None = None


class ResumeContent(BaseModel):
    """The editable, structured view of a parsed resume."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    years_of_experience: float | None = Field(default=None, ge=0, le=70)


class ResumeSummary(ORMModel):
    id: uuid.UUID
    label: str
    original_filename: str
    content_type: str
    file_size: int
    version: int
    is_default: bool
    parse_status: str
    parse_error: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ResumeDetail(ResumeSummary):
    content: ResumeContent
    raw_text_available: bool = False


class ResumeRename(BaseModel):
    label: str = Field(min_length=1, max_length=160)


class ResumeContentUpdate(BaseModel):
    """Partial update of the extracted fields; omitted fields are left as-is."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    job_titles: list[str] | None = None
    experience: list[ExperienceEntry] | None = None
    education: list[EducationEntry] | None = None
    certifications: list[CertificationEntry] | None = None
    years_of_experience: float | None = Field(default=None, ge=0, le=70)
