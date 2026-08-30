"""Match score and explanation schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import MatchQualificationKind


class Qualification(BaseModel):
    """One line item in the match explanation."""

    kind: MatchQualificationKind
    category: str
    label: str
    detail: str | None = None


class ComponentScore(BaseModel):
    name: str
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0)
    detail: str | None = None


class MatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    eligible: bool
    #: Populated when a hard eligibility rule rules the job out entirely.
    blocking_reasons: list[str] = Field(default_factory=list)
    strong: list[Qualification] = Field(default_factory=list)
    partial: list[Qualification] = Field(default_factory=list)
    missing: list[Qualification] = Field(default_factory=list)
    components: list[ComponentScore] = Field(default_factory=list)
    summary: str = ""
