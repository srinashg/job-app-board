"""Enumerations shared across models, schemas and services."""

from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """String enum whose value is used verbatim in the database and JSON."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class WorkArrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class ExperienceLevel(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"


EXPERIENCE_LEVEL_ORDER: dict[str, int] = {
    ExperienceLevel.INTERN.value: 0,
    ExperienceLevel.ENTRY.value: 1,
    ExperienceLevel.JUNIOR.value: 2,
    ExperienceLevel.MID.value: 3,
    ExperienceLevel.SENIOR.value: 4,
    ExperienceLevel.LEAD.value: 5,
    ExperienceLevel.PRINCIPAL.value: 6,
    ExperienceLevel.EXECUTIVE.value: 7,
}


class WorkAuthorization(StrEnum):
    CITIZEN = "citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    VISA_HOLDER = "visa_holder"
    NEEDS_SPONSORSHIP = "needs_sponsorship"
    OTHER = "other"


class SecurityClearance(StrEnum):
    NONE = "none"
    PUBLIC_TRUST = "public_trust"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"
    TS_SCI = "ts_sci"


CLEARANCE_ORDER: dict[str, int] = {
    SecurityClearance.NONE.value: 0,
    SecurityClearance.PUBLIC_TRUST.value: 1,
    SecurityClearance.CONFIDENTIAL.value: 2,
    SecurityClearance.SECRET.value: 3,
    SecurityClearance.TOP_SECRET.value: 4,
    SecurityClearance.TS_SCI.value: 5,
}


class JobStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    STALE = "stale"
    DUPLICATE = "duplicate"
    DISABLED = "disabled"
    SCAM = "scam"


class SourceType(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    CAREER_SITE = "career_site"
    MANUAL = "manual"


class RecommendationStatus(StrEnum):
    ACTIVE = "active"
    APPLIED = "applied"
    SKIPPED = "skipped"
    SAVED = "saved"
    CLOSED = "closed"
    REPLACED = "replaced"


class SkipReason(StrEnum):
    NOT_QUALIFIED = "not_qualified"
    ALREADY_APPLIED = "already_applied"
    CLOSED = "closed"
    LOCATION = "location"
    SALARY = "salary"
    SPONSORSHIP = "sponsorship"
    CLEARANCE = "clearance"
    EXPERIENCE_LEVEL = "experience_level"
    NOT_INTERESTED = "not_interested"


#: Skip reasons that mean "this listing is bad", not "not for me". Jobs skipped
#: for these reasons are replaced in the batch straight away.
REPLACEABLE_SKIP_REASONS: frozenset[str] = frozenset(
    {SkipReason.CLOSED.value, SkipReason.ALREADY_APPLIED.value}
)


class ApplicationStatus(StrEnum):
    TODO = "todo"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SKIPPED = "skipped"
    CLOSED = "closed"


#: Statuses that count as the employer having responded to the user.
RESPONSE_STATUSES: frozenset[str] = frozenset(
    {
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.OFFER.value,
        ApplicationStatus.REJECTED.value,
    }
)

#: Statuses that keep an application in the live pipeline.
OPEN_PIPELINE_STATUSES: frozenset[str] = frozenset(
    {
        ApplicationStatus.TODO.value,
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.OFFER.value,
    }
)


class BatchStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class BlacklistScope(StrEnum):
    COMPANY = "company"
    DOMAIN = "domain"
    JOB = "job"


class ConsentType(StrEnum):
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    RESUME_PROCESSING = "resume_processing"
    MARKETING_EMAIL = "marketing_email"


class MatchQualificationKind(StrEnum):
    STRONG = "strong"
    PARTIAL = "partial"
    MISSING = "missing"
