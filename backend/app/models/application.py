"""Application tracker, status history and recruiter contacts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.security import decrypt_text, encrypt_text
from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApplicationStatus

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.resume import Resume
    from app.models.user import User


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recruiter or hiring contact. Contact details are encrypted at rest."""

    __tablename__ = "contacts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    _email: Mapped[str | None] = mapped_column("email", Text, nullable=True)
    _phone: Mapped[str | None] = mapped_column("phone", Text, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="contacts")
    applications: Mapped[list["Application"]] = relationship(back_populates="contact")

    @property
    def email(self) -> str | None:
        return decrypt_text(self._email)

    @email.setter
    def email(self, value: str | None) -> None:
        self._email = encrypt_text(value)

    @property
    def phone(self) -> str | None:
        return decrypt_text(self._phone)

    @phone.setter
    def phone(self, value: str | None) -> None:
        self._phone = encrypt_text(value)


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Full history of one application, self-contained even if the job is purged."""

    __tablename__ = "applications"
    __table_args__ = (Index("ix_applications_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )

    # Denormalised copies so history survives job/company deletion.
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position_title: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Street address for hybrid/on-site roles; ``None`` when fully remote.
    work_address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    application_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    job_description_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ApplicationStatus.TODO.value, nullable=False, index=True
    )
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="applications")
    job: Mapped["Job | None"] = relationship()
    resume: Mapped["Resume | None"] = relationship(back_populates="applications")
    contact: Mapped[Contact | None] = relationship(back_populates="applications")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.occurred_at",
    )


class ApplicationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Status transition log for an application."""

    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    application: Mapped[Application] = relationship(back_populates="events")
