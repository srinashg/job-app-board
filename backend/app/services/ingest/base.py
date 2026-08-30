"""Shared types for job-source connectors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from app.models.enums import ExperienceLevel, WorkArrangement
from app.services.text import strip_html

_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|distributed|anywhere)\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\b(on[- ]?site|in[- ]?office|in[- ]?person)\b", re.IGNORECASE)

_LEVEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (ExperienceLevel.INTERN.value, re.compile(r"\b(intern|internship|co-?op)\b", re.IGNORECASE)),
    (
        ExperienceLevel.EXECUTIVE.value,
        re.compile(r"\b(chief|vp|vice president|head of|director)\b", re.IGNORECASE),
    ),
    (ExperienceLevel.PRINCIPAL.value, re.compile(r"\bprincipal|distinguished|fellow\b", re.IGNORECASE)),
    (ExperienceLevel.LEAD.value, re.compile(r"\b(lead|staff|manager)\b", re.IGNORECASE)),
    (ExperienceLevel.SENIOR.value, re.compile(r"\b(senior|sr\.?|iii|iv)\b", re.IGNORECASE)),
    (
        ExperienceLevel.ENTRY.value,
        re.compile(r"\b(entry[- ]level|new grad|graduate|associate i\b|junior|jr\.?)\b", re.IGNORECASE),
    ),
)

_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|or more|or greater)?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*years?"
    r"(?:\s+of)?\s+(?:relevant\s+|professional\s+|industry\s+|related\s+)?experience",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"\$\s?(\d{2,3}(?:,\d{3})|\d{2,3}(?:\.\d)?\s?[kK])\s*(?:-|–|to)\s*\$?\s?(\d{2,3}(?:,\d{3})|\d{2,3}(?:\.\d)?\s?[kK])"
)
_CLEARANCE_RE = re.compile(
    r"\b(ts\s*/\s*sci|top secret|secret|public trust|confidential)\b(?:[^.]{0,40}clearance)?",
    re.IGNORECASE,
)
_NO_SPONSORSHIP_RE = re.compile(
    r"(not?\s+(?:able\s+to\s+|be\s+)?(?:provide|offer|sponsor)\w*\s+(?:visa\s+)?sponsorship"
    r"|unable to sponsor|without sponsorship|no\s+visa\s+sponsorship"
    r"|does not (?:provide|offer) sponsorship)",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(
    r"(visa sponsorship (?:is )?available|will sponsor|we sponsor|sponsorship (?:is )?provided)",
    re.IGNORECASE,
)
_CITIZENSHIP_RE = re.compile(
    r"(u\.?s\.?\s+citizen(?:ship)?\s+(?:is\s+)?(?:required|only)|must be a u\.?s\.? citizen)",
    re.IGNORECASE,
)


@dataclass
class RawJob:
    """A posting as fetched from a source, before it is persisted."""

    external_id: str
    title: str
    description: str
    source_url: str
    company_name: str
    company_domain: str | None = None
    apply_url: str | None = None
    location: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None
    street_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    work_arrangement: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    date_posted: date | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


class SourceClient(Protocol):
    """Connector for one ATS/career-site provider."""

    source_type: str

    def fetch(self, external_slug: str, limit: int = 100) -> list[RawJob]:
        ...

    def is_open(self, job_url: str, external_id: str, external_slug: str) -> bool | None:
        """``True``/``False`` if the listing is still live, ``None`` if unknown."""
        ...


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y", "%d %B %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_iso_date(value: str | None) -> date | None:
    parsed = parse_iso_datetime(value)
    return parsed.date() if parsed else None


def infer_work_arrangement(location: str | None, description: str | None) -> str | None:
    """Decide remote/hybrid/on-site from the location line, then the description."""
    for text in (location, description):
        if not text:
            continue
        if _HYBRID_RE.search(text):
            return WorkArrangement.HYBRID.value
        if _REMOTE_RE.search(text):
            return WorkArrangement.REMOTE.value
        if _ONSITE_RE.search(text):
            return WorkArrangement.ONSITE.value
    return WorkArrangement.ONSITE.value if location else None


def infer_experience_level(title: str, description: str | None = None) -> str | None:
    for level, pattern in _LEVEL_PATTERNS:
        if pattern.search(title):
            return level
    if description:
        years = parse_min_years(description)
        if years is not None:
            if years >= 8:
                return ExperienceLevel.SENIOR.value
            if years >= 5:
                return ExperienceLevel.SENIOR.value
            if years >= 3:
                return ExperienceLevel.MID.value
            if years >= 1:
                return ExperienceLevel.JUNIOR.value
            return ExperienceLevel.ENTRY.value
    return ExperienceLevel.MID.value


def parse_min_years(description: str | None) -> float | None:
    if not description:
        return None
    matches = _YEARS_RE.findall(description)
    values = [float(value) for value in matches if value.isdigit()]
    return min(values) if values else None


def _money(token: str) -> int:
    text = token.replace(",", "").replace("$", "").strip()
    if text.lower().endswith("k"):
        return int(float(text[:-1]) * 1000)
    return int(float(text))


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """Best-effort annual salary range from a description. Missing is fine."""
    if not text:
        return None, None
    match = _SALARY_RE.search(text)
    if not match:
        return None, None
    try:
        low, high = _money(match.group(1)), _money(match.group(2))
    except ValueError:
        return None, None
    if low > high:
        low, high = high, low
    # Ignore hourly-looking numbers; MVP only tracks annual figures.
    if high < 10_000:
        return None, None
    return low, high


def parse_clearance(description: str | None) -> str | None:
    if not description:
        return None
    match = _CLEARANCE_RE.search(description)
    if not match:
        return None
    token = match.group(1).lower().replace(" ", "")
    mapping = {
        "ts/sci": "ts_sci",
        "topsecret": "top_secret",
        "secret": "secret",
        "publictrust": "public_trust",
        "confidential": "confidential",
    }
    return mapping.get(token)


def parse_sponsorship(description: str | None) -> bool | None:
    if not description:
        return None
    if _NO_SPONSORSHIP_RE.search(description):
        return False
    if _SPONSORSHIP_RE.search(description):
        return True
    return None


def parse_citizenship_required(description: str | None) -> bool:
    return bool(description and _CITIZENSHIP_RE.search(description))


def split_location(location: str | None) -> tuple[str | None, str | None, str | None]:
    """Split "San Francisco, CA, USA" into (city, region, country code)."""
    if not location:
        return None, None, None
    cleaned = _REMOTE_RE.sub("", location).strip(" ,-–|")
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if not parts:
        return None, None, None
    country_aliases = {
        "usa": "US", "us": "US", "united states": "US", "u.s.": "US",
        "canada": "CA", "united kingdom": "GB", "uk": "GB", "england": "GB",
        "germany": "DE", "france": "FR", "india": "IN", "australia": "AU",
        "ireland": "IE", "netherlands": "NL", "spain": "ES", "poland": "PL",
    }
    country = None
    if len(parts) > 1 and parts[-1].lower() in country_aliases:
        country = country_aliases[parts[-1].lower()]
        parts = parts[:-1]
    city = parts[0] if parts else None
    region = parts[1] if len(parts) > 1 else None
    if country is None and region and len(region) == 2 and region.isalpha():
        country = "US"
    return city, region, country


def clean_description(value: str | None) -> str:
    return strip_html(value)
