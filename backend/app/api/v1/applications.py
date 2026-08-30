"""Application tracker, history, contacts and the dashboard."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession, PageParams
from app.models.application import Application, Contact
from app.models.enums import ApplicationStatus
from app.models.job import Job
from app.models.resume import Resume
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    ContactRead,
    ContactWrite,
    DashboardStats,
)
from app.schemas.common import Message, Page
from app.services.applications import (
    TransitionError,
    change_status,
    create_application,
    dashboard_stats,
)

router = APIRouter(tags=["applications"])


def _get_application(db: DbSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
    application = db.execute(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user_id)
        .options(selectinload(Application.events), selectinload(Application.contact))
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


def _get_contact(db: DbSession, user_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None or contact.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.get("/applications", response_model=Page[ApplicationRead])
def list_applications(
    user: CurrentUser,
    db: DbSession,
    page: PageParams,
    status_filter: Annotated[list[ApplicationStatus] | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[ApplicationRead]:
    conditions = [Application.user_id == user.id]
    if status_filter:
        conditions.append(Application.status.in_([item.value for item in status_filter]))
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            func.lower(Application.company_name).like(pattern)
            | func.lower(Application.position_title).like(pattern)
        )

    total = db.execute(
        select(func.count()).select_from(Application).where(*conditions)
    ).scalar_one()
    rows = list(
        db.execute(
            select(Application)
            .where(*conditions)
            .order_by(Application.updated_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return Page[ApplicationRead](
        items=[ApplicationRead.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/applications", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED
)
def add_application(
    payload: ApplicationCreate, user: CurrentUser, db: DbSession
) -> ApplicationDetail:
    """Log an application, either from a tracked job or entered by hand."""
    job = None
    if payload.job_id is not None:
        job = db.get(Job, payload.job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    resume = None
    if payload.resume_id is not None:
        resume = db.get(Resume, payload.resume_id)
        if resume is None or resume.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    if payload.contact_id is not None:
        _get_contact(db, user.id, payload.contact_id)

    try:
        application = create_application(
            db,
            user,
            job=job,
            resume=resume,
            contact_id=payload.contact_id,
            company_name=payload.company_name,
            position_title=payload.position_title,
            location=payload.location,
            work_arrangement=payload.work_arrangement.value if payload.work_arrangement else None,
            work_address=payload.work_address,
            application_url=payload.application_url,
            status=payload.status.value,
            applied_at=payload.applied_at,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ApplicationDetail.model_validate(application)


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def read_application(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ApplicationDetail:
    return ApplicationDetail.model_validate(_get_application(db, user.id, application_id))


@router.patch("/applications/{application_id}", response_model=ApplicationDetail)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ApplicationDetail:
    application = _get_application(db, user.id, application_id)
    updates = payload.model_dump(exclude_unset=True)
    if "resume_id" in updates and updates["resume_id"] is not None:
        resume = db.get(Resume, updates["resume_id"])
        if resume is None or resume.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if "contact_id" in updates and updates["contact_id"] is not None:
        _get_contact(db, user.id, updates["contact_id"])
    for field, value in updates.items():
        setattr(application, field, value.value if hasattr(value, "value") else value)
    db.flush()
    return ApplicationDetail.model_validate(application)


@router.post("/applications/{application_id}/status", response_model=ApplicationDetail)
def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ApplicationDetail:
    application = _get_application(db, user.id, application_id)
    try:
        change_status(
            db,
            application,
            status=payload.status.value,
            note=payload.note,
            occurred_at=payload.occurred_at,
        )
    except TransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.refresh(application)
    return ApplicationDetail.model_validate(application)


@router.delete("/applications/{application_id}", response_model=Message)
def delete_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    application = _get_application(db, user.id, application_id)
    db.delete(application)
    db.flush()
    return Message(detail="Application deleted")


@router.get("/contacts", response_model=list[ContactRead])
def list_contacts(user: CurrentUser, db: DbSession) -> list[Contact]:
    stmt = select(Contact).where(Contact.user_id == user.id).order_by(Contact.name)
    return list(db.execute(stmt).scalars())


@router.post("/contacts", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def add_contact(payload: ContactWrite, user: CurrentUser, db: DbSession) -> Contact:
    contact = Contact(user_id=user.id)
    for field, value in payload.model_dump().items():
        setattr(contact, field, value)
    db.add(contact)
    db.flush()
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactRead)
def update_contact(
    contact_id: uuid.UUID, payload: ContactWrite, user: CurrentUser, db: DbSession
) -> Contact:
    contact = _get_contact(db, user.id, contact_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    db.flush()
    return contact


@router.delete("/contacts/{contact_id}", response_model=Message)
def delete_contact(contact_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    contact = _get_contact(db, user.id, contact_id)
    db.delete(contact)
    db.flush()
    return Message(detail="Contact deleted")


@router.get("/dashboard", response_model=DashboardStats, tags=["dashboard"])
def read_dashboard(user: CurrentUser, db: DbSession) -> DashboardStats:
    return dashboard_stats(db, user)
