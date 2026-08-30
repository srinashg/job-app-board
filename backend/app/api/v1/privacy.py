"""Privacy and account controls: export, resume purge, account deletion."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.security import verify_password
from app.models.application import Application, Contact
from app.models.resume import Resume
from app.models.user import ConsentRecord
from app.schemas.common import Message
from app.schemas.privacy import AccountDeleteRequest, DataExport, PrivacySummary
from app.services import resume_storage

router = APIRouter(prefix="/privacy", tags=["privacy"])

DELETE_CONFIRMATION = "DELETE"


@router.get("/summary", response_model=PrivacySummary)
def read_summary(user: CurrentUser, db: DbSession) -> PrivacySummary:
    """What personal data the account currently holds."""
    resumes = list(
        db.execute(
            select(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None))
        ).scalars()
    )
    consents = list(
        db.execute(
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user.id)
            .order_by(ConsentRecord.recorded_at.desc())
        ).scalars()
    )
    return PrivacySummary(
        resume_count=len(resumes),
        stored_resume_files=sum(1 for resume in resumes if resume.storage_path),
        application_count=len(
            list(db.execute(select(Application.id).where(Application.user_id == user.id)).all())
        ),
        contact_count=len(
            list(db.execute(select(Contact.id).where(Contact.user_id == user.id)).all())
        ),
        consents=[
            {
                "consent_type": consent.consent_type,
                "granted": consent.granted,
                "recorded_at": consent.recorded_at.isoformat(),
            }
            for consent in consents
        ],
        deletion_requested_at=user.deletion_requested_at,
    )


@router.get("/export", response_model=DataExport)
def export_data(user: CurrentUser, db: DbSession) -> DataExport:
    """Everything the account holds, in one JSON document."""
    resumes = list(db.execute(select(Resume).where(Resume.user_id == user.id)).scalars())
    applications = list(
        db.execute(select(Application).where(Application.user_id == user.id)).scalars()
    )
    contacts = list(db.execute(select(Contact).where(Contact.user_id == user.id)).scalars())
    consents = list(
        db.execute(select(ConsentRecord).where(ConsentRecord.user_id == user.id)).scalars()
    )

    return DataExport(
        generated_at=datetime.now(timezone.utc),
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at.isoformat(),
        },
        profile=(
            {
                "headline": user.profile.headline,
                "phone": user.profile.phone,
                "street_address": user.profile.street_address,
                "city": user.profile.city,
                "region": user.profile.region,
                "postal_code": user.profile.postal_code,
                "country": user.profile.country,
                "current_title": user.profile.current_title,
            }
            if user.profile
            else None
        ),
        eligibility=(
            {
                "work_authorization": user.eligibility.work_authorization,
                "requires_sponsorship": user.eligibility.requires_sponsorship,
                "security_clearance": user.eligibility.security_clearance,
                "willing_to_relocate": user.eligibility.willing_to_relocate,
                "minimum_salary": user.eligibility.minimum_salary,
            }
            if user.eligibility
            else None
        ),
        preferences=(
            {
                "work_arrangements": user.preferences.work_arrangements,
                "preferred_locations": user.preferences.preferred_locations,
                "desired_titles": user.preferences.desired_titles,
                "technologies": user.preferences.technologies,
                "excluded_companies": user.preferences.excluded_companies,
                "match_threshold": user.preferences.match_threshold,
            }
            if user.preferences
            else None
        ),
        consents=[
            {
                "consent_type": consent.consent_type,
                "granted": consent.granted,
                "recorded_at": consent.recorded_at.isoformat(),
            }
            for consent in consents
        ],
        resumes=[
            {
                "id": str(resume.id),
                "label": resume.label,
                "original_filename": resume.original_filename,
                "version": resume.version,
                "deleted": resume.deleted_at is not None,
                "content": resume.content,
            }
            for resume in resumes
        ],
        applications=[
            {
                "id": str(application.id),
                "company_name": application.company_name,
                "position_title": application.position_title,
                "status": application.status,
                "applied_at": application.applied_at.isoformat() if application.applied_at else None,
                "application_url": application.application_url,
                "notes": application.notes,
            }
            for application in applications
        ],
        contacts=[
            {
                "id": str(contact.id),
                "name": contact.name,
                "email": contact.email,
                "phone": contact.phone,
                "company_name": contact.company_name,
            }
            for contact in contacts
        ],
    )


@router.delete("/resumes", response_model=Message)
def delete_all_resumes(user: CurrentUser, db: DbSession) -> Message:
    """Purge every stored resume file and its extracted content."""
    resumes = list(db.execute(select(Resume).where(Resume.user_id == user.id)).scalars())
    now = datetime.now(timezone.utc)
    for resume in resumes:
        resume.storage_path = None
        resume.raw_text = None
        resume.parsed_data = {}
        resume.edited_data = {}
        resume.is_default = False
        if resume.deleted_at is None:
            resume.deleted_at = now
    removed_files = resume_storage.delete_all_for_user(user.id)
    db.flush()
    return Message(
        detail=f"Deleted {len(resumes)} resume record(s) and {removed_files} stored file(s)"
    )


@router.delete("/account", response_model=Message)
def delete_account(payload: AccountDeleteRequest, user: CurrentUser, db: DbSession) -> Message:
    """Permanently delete the account and everything attached to it."""
    if payload.confirmation != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Type "{DELETE_CONFIRMATION}" to confirm account deletion',
        )
    if user.hashed_password:
        if not payload.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirm your password to delete the account",
            )
        if not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Password is incorrect"
            )

    resume_storage.delete_all_for_user(user.id)
    # Every child table cascades from users, so one delete clears the account.
    db.delete(user)
    db.flush()
    return Message(detail="Account and all associated data deleted")
