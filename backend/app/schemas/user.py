"""User, profile, eligibility, preferences and consent schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import (
    ConsentType,
    ExperienceLevel,
    SecurityClearance,
    WorkArrangement,
    WorkAuthorization,
)
from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    is_email_verified: bool
    onboarding_completed_at: datetime | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)


class ProfileRead(ORMModel):
    headline: str | None = None
    phone: str | None = None
    street_address: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    years_of_experience: float | None = None
    current_title: str | None = None


class ProfileUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    street_address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    years_of_experience: float | None = Field(default=None, ge=0, le=70)
    current_title: str | None = Field(default=None, max_length=200)


class EligibilityRead(ORMModel):
    work_authorization: str
    requires_sponsorship: bool
    security_clearance: str
    willing_to_relocate: bool
    authorized_countries: list[str]
    minimum_salary: int | None = None
    earliest_start_date: date | None = None
    total_years_experience: float | None = None


class EligibilityUpdate(BaseModel):
    work_authorization: WorkAuthorization | None = None
    requires_sponsorship: bool | None = None
    security_clearance: SecurityClearance | None = None
    willing_to_relocate: bool | None = None
    authorized_countries: list[str] | None = None
    minimum_salary: int | None = Field(default=None, ge=0)
    earliest_start_date: date | None = None
    total_years_experience: float | None = Field(default=None, ge=0, le=70)


class PreferencesRead(ORMModel):
    work_arrangements: list[str]
    preferred_locations: list[str]
    location_radius_miles: int | None = None
    desired_titles: list[str]
    excluded_titles: list[str]
    technologies: list[str]
    industries: list[str]
    excluded_companies: list[str]
    experience_levels: list[str]
    minimum_salary: int | None = None
    max_days_since_posted: int | None = None
    match_threshold: int


class PreferencesUpdate(BaseModel):
    work_arrangements: list[WorkArrangement] | None = None
    preferred_locations: list[str] | None = None
    location_radius_miles: int | None = Field(default=None, ge=0, le=500)
    desired_titles: list[str] | None = None
    excluded_titles: list[str] | None = None
    technologies: list[str] | None = None
    industries: list[str] | None = None
    excluded_companies: list[str] | None = None
    experience_levels: list[ExperienceLevel] | None = None
    minimum_salary: int | None = Field(default=None, ge=0)
    max_days_since_posted: int | None = Field(default=None, ge=1, le=365)
    match_threshold: int | None = Field(default=None, ge=0, le=100)


class ConsentRead(ORMModel):
    id: uuid.UUID
    consent_type: str
    granted: bool
    document_version: str | None = None
    recorded_at: datetime


class ConsentUpdate(BaseModel):
    consent_type: ConsentType
    granted: bool
    document_version: str | None = Field(default=None, max_length=40)


class OnboardingRequest(BaseModel):
    """Single call that completes onboarding steps 1-4."""

    profile: ProfileUpdate | None = None
    eligibility: EligibilityUpdate | None = None
    preferences: PreferencesUpdate | None = None
    consents: list[ConsentUpdate] = Field(default_factory=list)


class OnboardingStatus(BaseModel):
    completed: bool
    has_profile: bool
    has_eligibility: bool
    has_preferences: bool
    has_resume: bool
    next_step: str | None = None
