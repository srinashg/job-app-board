"""Duplicate detection for job listings (feature 5).

Two layers:

* a **fingerprint** — company + normalised title + normalised location — which
  catches the same role posted through two sources; and
* a **similarity check** against same-company jobs, which catches near-identical
  postings whose titles differ cosmetically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.job import Job
from app.services.text import content_hash, jaccard, normalize, normalize_title, tokenize

#: Title+description similarity above which two same-company postings are the
#: same role. Tuned to be conservative: a false merge hides a real job.
SIMILARITY_THRESHOLD = 0.82
TITLE_SIMILARITY_FLOOR = 0.7


def compute_fingerprint(
    company_slug: str, title: str | None, location: str | None
) -> str:
    """Stable hash identifying "this role at this company in this place"."""
    return content_hash(company_slug, normalize_title(title), _location_key(location))


def _location_key(location: str | None) -> str:
    normalized = normalize(location)
    if not normalized:
        return "unspecified"
    # "Remote - US" and "Remote (US)" should land on the same key.
    if "remote" in normalized:
        return "remote"
    return normalized


@dataclass
class DuplicateMatch:
    job: Job
    reason: str
    similarity: float


def similarity(
    left_title: str | None,
    left_description: str | None,
    right_title: str | None,
    right_description: str | None,
) -> float:
    """Blend of title and description similarity, in ``[0, 1]``."""
    title_score = jaccard(
        tokenize(normalize_title(left_title)), tokenize(normalize_title(right_title))
    )
    description_score = jaccard(
        tokenize(left_description or ""), tokenize(right_description or "")
    )
    return 0.6 * title_score + 0.4 * description_score


def find_duplicate(
    db: Session,
    *,
    company_id: uuid.UUID,
    fingerprint: str,
    title: str,
    description: str,
    exclude_job_id: uuid.UUID | None = None,
) -> DuplicateMatch | None:
    """Find an existing job this posting duplicates, if any."""
    stmt = select(Job).where(
        Job.company_id == company_id,
        Job.status.notin_([JobStatus.DUPLICATE.value, JobStatus.DISABLED.value]),
    )
    if exclude_job_id is not None:
        stmt = stmt.where(Job.id != exclude_job_id)
    candidates = list(db.execute(stmt).scalars())
    if not candidates:
        return None

    for candidate in candidates:
        if candidate.fingerprint == fingerprint:
            return DuplicateMatch(job=candidate, reason="fingerprint", similarity=1.0)

    best: DuplicateMatch | None = None
    for candidate in candidates:
        title_score = jaccard(
            tokenize(normalize_title(title)), tokenize(normalize_title(candidate.title))
        )
        if title_score < TITLE_SIMILARITY_FLOOR:
            continue
        score = similarity(title, description, candidate.title, candidate.description)
        if score >= SIMILARITY_THRESHOLD and (best is None or score > best.similarity):
            best = DuplicateMatch(job=candidate, reason="similarity", similarity=score)
    return best


def canonical_job(job: Job) -> Job:
    """Follow the duplicate chain to the job that should actually be shown."""
    seen: set[uuid.UUID] = set()
    current = job
    while current.duplicate_of is not None and current.id not in seen:
        seen.add(current.id)
        current = current.duplicate_of
    return current
