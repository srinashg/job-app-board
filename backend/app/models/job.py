"""Companies, job sources, job listings and moderation blacklists."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import JobStatus, SourceType

if TYPE_CHECKING:
    from app.models.recommendation import Recommendation


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    careers_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size: Mapped[str | None] = mapped_column(String(60), nullable=True)
    headquarters: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    sources: Mapped[list["JobSource"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class JobSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A legitimate career-site/ATS feed we are allowed to fetch from."""

    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source_type", "external_slug", name="uq_source_type_slug"),
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(40), default=SourceType.GREENHOUSE.value, nullable=False
    )
    #: Board identifier on the ATS, e.g. the Greenhouse board token.
    external_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    company: Mapped[Company | None] = relationship(back_populates="sources")
    jobs: Mapped[list["Job"]] = relationship(back_populates="source")


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_job_source_external"),
        Index("ix_jobs_status_posted", "status", "date_posted"),
        Index("ix_jobs_fingerprint", "fingerprint"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_sources.id", ondelete="SET NULL"), nullable=True
    )
    #: Identifier of the posting inside its source system.
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Immutable copy of the description as first fetched, shown on applications.
    description_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Street address, required for hybrid/on-site roles when the source has it.
    street_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)

    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(20), nullable=True)

    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    min_years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    required_skills: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    preferred_skills: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)

    requires_clearance: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sponsorship_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    citizenship_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    date_posted: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    apply_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.ACTIVE.value, nullable=False, index=True
    )
    #: Stable hash of company + normalised title + location, used for dedupe.
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    moderation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="jobs")
    source: Mapped[JobSource | None] = relationship(back_populates="jobs")
    duplicate_of: Mapped["Job | None"] = relationship(remote_side="Job.id")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="job")

    @property
    def is_recommendable(self) -> bool:
        return self.status == JobStatus.ACTIVE.value and self.duplicate_of_id is None


class Blacklist(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-managed blocklist for jobs, companies and domains."""

    __tablename__ = "blacklists"
    __table_args__ = (UniqueConstraint("scope", "value", name="uq_blacklist_scope_value"),)

    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Company slug, bare domain or job id, depending on ``scope``.
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
