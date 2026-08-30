"""User account, profile, eligibility rules, preferences and consent."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import decrypt_text, encrypt_text
from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ExperienceLevel,
    SecurityClearance,
    UserRole,
    WorkArrangement,
    WorkAuthorization,
)

if TYPE_CHECKING:
    from app.models.application import Application, Contact
    from app.models.recommendation import Batch, Recommendation
    from app.models.resume import Resume


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    eligibility: Mapped["EligibilityProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    preferences: Mapped["JobPreferences | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    consents: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    batches: Mapped[list["Batch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_completed_at is not None


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Link between a local user and an external OAuth 2.0 identity."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id", name="uq_oauth_identity"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Personal details. Free-text personal fields are encrypted at rest."""

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    _phone: Mapped[str | None] = mapped_column("phone", Text, nullable=True)
    _street_address: Mapped[str | None] = mapped_column("street_address", Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    years_of_experience: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    user: Mapped[User] = relationship(back_populates="profile")

    @property
    def phone(self) -> str | None:
        return decrypt_text(self._phone)

    @phone.setter
    def phone(self, value: str | None) -> None:
        self._phone = encrypt_text(value)

    @property
    def street_address(self) -> str | None:
        return decrypt_text(self._street_address)

    @street_address.setter
    def street_address(self, value: str | None) -> None:
        self._street_address = encrypt_text(value)


class EligibilityProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Hard rules a job must satisfy before it can ever be recommended."""

    __tablename__ = "eligibility_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    work_authorization: Mapped[str] = mapped_column(
        String(40), default=WorkAuthorization.CITIZEN.value, nullable=False
    )
    requires_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    security_clearance: Mapped[str] = mapped_column(
        String(40), default=SecurityClearance.NONE.value, nullable=False
    )
    willing_to_relocate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorized_countries: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    minimum_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    earliest_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_years_experience: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)

    user: Mapped[User] = relationship(back_populates="eligibility")


class JobPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Soft preferences and the saved state of the filter panel."""

    __tablename__ = "job_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    work_arrangements: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: [WorkArrangement.REMOTE.value],
        server_default='["remote"]',
        nullable=False,
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    location_radius_miles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_titles: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    excluded_titles: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    technologies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    industries: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    excluded_companies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    experience_levels: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: [ExperienceLevel.MID.value],
        server_default='["mid"]',
        nullable=False,
    )
    minimum_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_days_since_posted: Mapped[int | None] = mapped_column(Integer, default=30, nullable=True)
    match_threshold: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    extra_filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class ConsentRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only audit trail of consent grants and withdrawals."""

    __tablename__ = "consent_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(60), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    document_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="consents")
