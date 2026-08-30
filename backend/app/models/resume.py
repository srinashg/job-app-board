"""Resume files, parsed content and version management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.user import User


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded resume version.

    ``parsed_data`` holds the machine-extracted content and ``edited_data`` the
    user's corrections; :attr:`content` merges them so downstream matching
    always reads the user-approved version.
    """

    __tablename__ = "resumes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    edited_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    parse_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="resumes")
    applications: Mapped[list["Application"]] = relationship(back_populates="resume")

    @property
    def content(self) -> dict[str, Any]:
        """Parsed content with the user's edits applied on top, field by field."""
        merged: dict[str, Any] = dict(self.parsed_data or {})
        merged.update(self.edited_data or {})
        return merged

    @property
    def skills(self) -> list[str]:
        return list(self.content.get("skills") or [])

    @property
    def job_titles(self) -> list[str]:
        return list(self.content.get("job_titles") or [])

    @property
    def years_of_experience(self) -> float | None:
        value = self.content.get("years_of_experience")
        return float(value) if value is not None else None
