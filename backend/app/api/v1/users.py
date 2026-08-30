"""Profile, eligibility rules, preferences, consent and onboarding."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.user import ConsentRecord, EligibilityProfile, JobPreferences, User, UserProfile
from app.schemas.common import Message
from app.schemas.user import (
    ConsentRead,
    ConsentUpdate,
    EligibilityRead,
    EligibilityUpdate,
    OnboardingRequest,
    OnboardingStatus,
    PreferencesRead,
    PreferencesUpdate,
    ProfileRead,
    ProfileUpdate,
    UserRead,
    UserUpdate,
)
from app.models.resume import Resume

router = APIRouter(prefix="/me", tags=["profile"])

#: Profile fields whose setters encrypt the value, so they cannot be set with
#: a plain ``setattr`` loop over the column names.
ENCRYPTED_PROFILE_FIELDS = {"phone", "street_address"}


def _get_profile(db: DbSession, user: User) -> UserProfile:
    if user.profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.flush()
        db.refresh(user)
        return profile
    return user.profile


def _get_eligibility(db: DbSession, user: User) -> EligibilityProfile:
    if user.eligibility is None:
        eligibility = EligibilityProfile(user_id=user.id)
        db.add(eligibility)
        db.flush()
        db.refresh(user)
        return eligibility
    return user.eligibility


def _get_preferences(db: DbSession, user: User) -> JobPreferences:
    if user.preferences is None:
        preferences = JobPreferences(user_id=user.id)
        db.add(preferences)
        db.flush()
        db.refresh(user)
        return preferences
    return user.preferences


def _apply(target: object, payload: object) -> None:
    """Copy the fields the client actually sent onto a model instance."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, field, value.value if hasattr(value, "value") else value)


@router.get("", response_model=UserRead)
def read_account(user: CurrentUser) -> User:
    return user


@router.patch("", response_model=UserRead)
def update_account(payload: UserUpdate, user: CurrentUser) -> User:
    _apply(user, payload)
    return user


@router.get("/profile", response_model=ProfileRead)
def read_profile(user: CurrentUser, db: DbSession) -> UserProfile:
    return _get_profile(db, user)


@router.put("/profile", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserProfile:
    profile = _get_profile(db, user)
    _apply(profile, payload)
    return profile


@router.get("/eligibility", response_model=EligibilityRead)
def read_eligibility(user: CurrentUser, db: DbSession) -> EligibilityProfile:
    return _get_eligibility(db, user)


@router.put("/eligibility", response_model=EligibilityRead)
def update_eligibility(
    payload: EligibilityUpdate, user: CurrentUser, db: DbSession
) -> EligibilityProfile:
    eligibility = _get_eligibility(db, user)
    _apply(eligibility, payload)
    return eligibility


@router.get("/preferences", response_model=PreferencesRead)
def read_preferences(user: CurrentUser, db: DbSession) -> JobPreferences:
    return _get_preferences(db, user)


@router.put("/preferences", response_model=PreferencesRead)
def update_preferences(
    payload: PreferencesUpdate, user: CurrentUser, db: DbSession
) -> JobPreferences:
    preferences = _get_preferences(db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if isinstance(value, list):
            value = [item.value if hasattr(item, "value") else item for item in value]
        setattr(preferences, field, value)
    return preferences


@router.get("/consents", response_model=list[ConsentRead])
def list_consents(user: CurrentUser, db: DbSession) -> list[ConsentRecord]:
    stmt = (
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user.id)
        .order_by(ConsentRecord.recorded_at.desc())
    )
    return list(db.execute(stmt).scalars())


@router.post("/consents", response_model=ConsentRead, status_code=status.HTTP_201_CREATED)
def record_consent(payload: ConsentUpdate, user: CurrentUser, db: DbSession) -> ConsentRecord:
    record = ConsentRecord(
        user_id=user.id,
        consent_type=payload.consent_type.value,
        granted=payload.granted,
        document_version=payload.document_version,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


@router.get("/onboarding", response_model=OnboardingStatus)
def onboarding_status(user: CurrentUser, db: DbSession) -> OnboardingStatus:
    has_resume = (
        db.execute(
            select(Resume.id).where(Resume.user_id == user.id, Resume.deleted_at.is_(None)).limit(1)
        ).first()
        is not None
    )
    has_profile = user.profile is not None and bool(user.profile.current_title or user.profile.city)
    has_eligibility = user.eligibility is not None
    has_preferences = user.preferences is not None and bool(
        user.preferences.desired_titles or user.preferences.technologies
    )

    next_step = None
    if not has_profile:
        next_step = "profile"
    elif not has_eligibility:
        next_step = "eligibility"
    elif not has_preferences:
        next_step = "preferences"
    elif not has_resume:
        next_step = "resume"

    return OnboardingStatus(
        completed=user.is_onboarded,
        has_profile=has_profile,
        has_eligibility=has_eligibility,
        has_preferences=has_preferences,
        has_resume=has_resume,
        next_step=next_step,
    )


@router.post("/onboarding", response_model=OnboardingStatus)
def complete_onboarding(
    payload: OnboardingRequest, user: CurrentUser, db: DbSession
) -> OnboardingStatus:
    """Save everything the onboarding wizard collected and mark it finished."""
    if payload.profile is not None:
        _apply(_get_profile(db, user), payload.profile)
    if payload.eligibility is not None:
        _apply(_get_eligibility(db, user), payload.eligibility)
    if payload.preferences is not None:
        preferences = _get_preferences(db, user)
        for field, value in payload.preferences.model_dump(exclude_unset=True).items():
            if isinstance(value, list):
                value = [item.value if hasattr(item, "value") else item for item in value]
            setattr(preferences, field, value)
    for consent in payload.consents:
        db.add(
            ConsentRecord(
                user_id=user.id,
                consent_type=consent.consent_type.value,
                granted=consent.granted,
                document_version=consent.document_version,
                recorded_at=datetime.now(timezone.utc),
            )
        )

    user.onboarding_completed_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(user)
    return onboarding_status(user, db)
