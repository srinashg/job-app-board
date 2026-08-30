"""Resume upload, parsing, editing and version management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.models.resume import Resume
from app.schemas.common import Message
from app.schemas.resume import (
    ResumeContent,
    ResumeContentUpdate,
    ResumeDetail,
    ResumeRename,
    ResumeSummary,
)
from app.services import resume_storage
from app.services.resume_parser import ResumeParseError, parse_resume_file
from app.services.taxonomy import canonical_skills

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _get_resume(db: DbSession, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user_id or resume.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def _to_detail(resume: Resume) -> ResumeDetail:
    return ResumeDetail(
        **ResumeSummary.model_validate(resume).model_dump(),
        content=ResumeContent.model_validate(resume.content),
        raw_text_available=bool(resume.raw_text),
    )


@router.get("", response_model=list[ResumeSummary])
def list_resumes(user: CurrentUser, db: DbSession) -> list[Resume]:
    stmt = (
        select(Resume)
        .where(Resume.user_id == user.id, Resume.deleted_at.is_(None))
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


@router.post("", response_model=ResumeDetail, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(..., description="PDF, DOCX or plain-text resume"),
    label: str | None = Form(default=None),
    make_default: bool = Form(default=False),
) -> ResumeDetail:
    """Upload a resume, store it and extract its content for the user to edit."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty")
    if len(data) > settings.max_resume_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Resumes must be {settings.max_resume_bytes // (1024 * 1024)}MB or smaller",
        )

    content_type = file.content_type or "application/octet-stream"
    version = (
        db.execute(
            select(func.count()).select_from(Resume).where(Resume.user_id == user.id)
        ).scalar_one()
        + 1
    )
    has_existing_default = (
        db.execute(
            select(Resume.id)
            .where(
                Resume.user_id == user.id,
                Resume.deleted_at.is_(None),
                Resume.is_default.is_(True),
            )
            .limit(1)
        ).first()
        is not None
    )

    resume = Resume(
        user_id=user.id,
        label=(label or file.filename or f"Resume {version}").strip()[:160],
        original_filename=file.filename or "resume",
        content_type=content_type,
        file_size=len(data),
        checksum=resume_storage.checksum(data),
        version=version,
        is_default=make_default or not has_existing_default,
        parse_status="pending",
    )
    db.add(resume)
    db.flush()

    if resume.is_default:
        _clear_other_defaults(db, user.id, resume.id)

    try:
        raw_text, parsed = parse_resume_file(data, content_type, file.filename)
    except ResumeParseError as exc:
        # Keep the upload: the user can still select it and fill fields in by hand.
        resume.parse_status = "failed"
        resume.parse_error = str(exc)
        resume.parsed_data = {}
    else:
        resume.raw_text = raw_text
        parsed_dict = parsed.to_dict()
        parsed_dict["skills"] = canonical_skills(parsed_dict.get("skills"))
        resume.parsed_data = parsed_dict
        resume.parse_status = "parsed"
        resume.parse_error = None
        resume.parsed_at = datetime.now(timezone.utc)

    resume.storage_path = resume_storage.save(user.id, resume.id, data, content_type)
    db.flush()
    return _to_detail(resume)


@router.get("/{resume_id}", response_model=ResumeDetail)
def read_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeDetail:
    return _to_detail(_get_resume(db, user.id, resume_id))


@router.get("/{resume_id}/file")
def download_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    resume = _get_resume(db, user.id, resume_id)
    data = resume_storage.read(resume.storage_path)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="The stored file is no longer available"
        )
    return Response(
        content=data,
        media_type=resume.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{resume.original_filename}"'
        },
    )


@router.patch("/{resume_id}", response_model=ResumeDetail)
def rename_resume(
    resume_id: uuid.UUID, payload: ResumeRename, user: CurrentUser, db: DbSession
) -> ResumeDetail:
    resume = _get_resume(db, user.id, resume_id)
    resume.label = payload.label.strip()
    db.flush()
    return _to_detail(resume)


@router.put("/{resume_id}/content", response_model=ResumeDetail)
def edit_resume_content(
    resume_id: uuid.UUID, payload: ResumeContentUpdate, user: CurrentUser, db: DbSession
) -> ResumeDetail:
    """Save the user's corrections to the extracted fields.

    Edits are stored separately from the parse output, so re-parsing never
    silently discards them.
    """
    resume = _get_resume(db, user.id, resume_id)
    edits = dict(resume.edited_data or {})
    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        if field == "skills" and value is not None:
            value = canonical_skills(value)
        edits[field] = value
    resume.edited_data = edits
    db.flush()
    return _to_detail(resume)


@router.post("/{resume_id}/reparse", response_model=ResumeDetail)
def reparse_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeDetail:
    """Re-run extraction on the stored file, keeping the user's edits on top."""
    resume = _get_resume(db, user.id, resume_id)
    data = resume_storage.read(resume.storage_path)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The original file is no longer stored, so it cannot be re-parsed",
        )
    try:
        raw_text, parsed = parse_resume_file(data, resume.content_type, resume.original_filename)
    except ResumeParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    parsed_dict = parsed.to_dict()
    parsed_dict["skills"] = canonical_skills(parsed_dict.get("skills"))
    resume.raw_text = raw_text
    resume.parsed_data = parsed_dict
    resume.parse_status = "parsed"
    resume.parse_error = None
    resume.parsed_at = datetime.now(timezone.utc)
    db.flush()
    return _to_detail(resume)


@router.post("/{resume_id}/default", response_model=ResumeDetail)
def set_default_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeDetail:
    """Pick the resume used for matching and pre-selected on new applications."""
    resume = _get_resume(db, user.id, resume_id)
    resume.is_default = True
    _clear_other_defaults(db, user.id, resume.id)
    db.flush()
    return _to_detail(resume)


@router.delete("/{resume_id}", response_model=Message)
def delete_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    """Delete a resume version and the stored file behind it.

    The row is soft-deleted so applications keep pointing at the version that
    was actually sent, but the file bytes and extracted text are removed.
    """
    resume = _get_resume(db, user.id, resume_id)
    resume_storage.delete(resume.storage_path)
    resume.storage_path = None
    resume.raw_text = None
    resume.parsed_data = {}
    resume.edited_data = {}
    resume.deleted_at = datetime.now(timezone.utc)
    was_default = resume.is_default
    resume.is_default = False
    db.flush()

    if was_default:
        replacement = db.execute(
            select(Resume)
            .where(Resume.user_id == user.id, Resume.deleted_at.is_(None))
            .order_by(Resume.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if replacement is not None:
            replacement.is_default = True
            db.flush()
    return Message(detail="Resume deleted")


def _clear_other_defaults(db: DbSession, user_id: uuid.UUID, keep_id: uuid.UUID) -> None:
    others = db.execute(
        select(Resume).where(
            Resume.user_id == user_id, Resume.id != keep_id, Resume.is_default.is_(True)
        )
    ).scalars()
    for other in others:
        other.is_default = False
