"""Five-job batches and the recommendations inside them."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BatchStatus, RecommendationStatus

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.user import User


class Batch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A set of jobs the user must fully resolve before the next set unlocks."""

    __tablename__ = "batches"
    __table_args__ = (Index("ix_batches_user_status", "user_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=BatchStatus.ACTIVE.value, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="batches")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="Recommendation.position"
    )

    @property
    def live_recommendations(self) -> list["Recommendation"]:
        """Recommendations still counted towards this batch (replacements excluded)."""
        return [
            rec
            for rec in self.recommendations
            if rec.status != RecommendationStatus.REPLACED.value
        ]

    @property
    def resolved_count(self) -> int:
        return sum(1 for rec in self.live_recommendations if rec.is_resolved)

    @property
    def is_complete(self) -> bool:
        live = self.live_recommendations
        return bool(live) and all(rec.is_resolved for rec in live)


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One job surfaced to one user, with its match explanation."""

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_recommendation_user_job"),
        Index("ix_recommendations_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=RecommendationStatus.ACTIVE.value, nullable=False
    )
    match_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Serialised MatchResult: qualification breakdown and component scores.
    match_explanation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    skip_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skip_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set when this recommendation was swapped in for a closed/duplicate job.
    replaced_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="recommendations")
    job: Mapped["Job"] = relationship(back_populates="recommendations")
    batch: Mapped[Batch | None] = relationship(back_populates="recommendations")

    #: Terminal states. ``SAVED`` deliberately is not one: saving a job for later
    #: does not resolve it, the user still has to apply or skip.
    RESOLVED_STATUSES = frozenset(
        {
            RecommendationStatus.APPLIED.value,
            RecommendationStatus.SKIPPED.value,
            RecommendationStatus.CLOSED.value,
        }
    )

    @property
    def is_resolved(self) -> bool:
        return self.status in self.RESOLVED_STATUSES
