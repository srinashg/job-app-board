"""Deterministic job matching: hard eligibility gates plus weighted scoring.

The engine returns a :class:`MatchResult` whose ``strong``/``partial``/``missing``
lists are what the UI renders as the match explanation, so every point of the
score is traceable to a line the user can read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from app.models.enums import (
    CLEARANCE_ORDER,
    EXPERIENCE_LEVEL_ORDER,
    MatchQualificationKind,
    WorkArrangement,
    WorkAuthorization,
)
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import EligibilityProfile, JobPreferences, UserProfile
from app.schemas.matching import ComponentScore, MatchResult, Qualification
from app.services.taxonomy import canonical_skills
from app.services.text import jaccard, normalize, normalize_title, overlap_ratio, tokenize

#: Component weights. They need not sum to 1: the score is the weighted mean of
#: the components that actually apply to this job/user pair.
WEIGHTS: dict[str, float] = {
    "skills": 0.30,
    "technologies": 0.20,
    "title": 0.20,
    "experience": 0.15,
    "location": 0.10,
    "salary": 0.05,
}


@dataclass
class CandidateProfile:
    """Everything the matcher needs about the user, gathered once per run."""

    skills: set[str]
    technologies: set[str]
    titles: list[str]
    years_of_experience: float | None
    experience_levels: list[str]
    desired_titles: list[str]
    excluded_titles: list[str]
    preferred_locations: list[str]
    work_arrangements: list[str]
    minimum_salary: int | None
    industries: list[str]
    excluded_companies: list[str]
    match_threshold: int
    max_days_since_posted: int | None
    requires_sponsorship: bool
    work_authorization: str
    security_clearance: str
    willing_to_relocate: bool
    authorized_countries: list[str]
    home_location: str | None

    @classmethod
    def build(
        cls,
        *,
        eligibility: EligibilityProfile | None,
        preferences: JobPreferences | None,
        resume: Resume | None = None,
        profile: UserProfile | None = None,
    ) -> "CandidateProfile":
        resume_skills = canonical_skills(resume.skills if resume else [])
        preference_techs = canonical_skills(preferences.technologies if preferences else [])
        years = None
        if eligibility is not None and eligibility.total_years_experience is not None:
            years = float(eligibility.total_years_experience)
        elif resume is not None and resume.years_of_experience is not None:
            years = resume.years_of_experience
        elif profile is not None and profile.years_of_experience is not None:
            years = float(profile.years_of_experience)

        titles = list(resume.job_titles) if resume else []
        if profile is not None and profile.current_title:
            titles = [profile.current_title, *titles]

        home_parts = [profile.city, profile.region] if profile else []
        home_location = ", ".join(part for part in home_parts if part) or None

        return cls(
            skills=set(resume_skills) | set(preference_techs),
            technologies=set(preference_techs) or set(resume_skills),
            titles=titles,
            years_of_experience=years,
            experience_levels=list(preferences.experience_levels) if preferences else [],
            desired_titles=list(preferences.desired_titles) if preferences else [],
            excluded_titles=list(preferences.excluded_titles) if preferences else [],
            preferred_locations=list(preferences.preferred_locations) if preferences else [],
            work_arrangements=list(preferences.work_arrangements) if preferences else [],
            minimum_salary=(
                preferences.minimum_salary
                if preferences and preferences.minimum_salary is not None
                else (eligibility.minimum_salary if eligibility else None)
            ),
            industries=list(preferences.industries) if preferences else [],
            excluded_companies=[
                normalize(name) for name in (preferences.excluded_companies if preferences else [])
            ],
            match_threshold=preferences.match_threshold if preferences else 0,
            max_days_since_posted=preferences.max_days_since_posted if preferences else None,
            requires_sponsorship=bool(eligibility.requires_sponsorship) if eligibility else False,
            work_authorization=(
                eligibility.work_authorization if eligibility else WorkAuthorization.CITIZEN.value
            ),
            security_clearance=eligibility.security_clearance if eligibility else "none",
            willing_to_relocate=bool(eligibility.willing_to_relocate) if eligibility else False,
            authorized_countries=list(eligibility.authorized_countries) if eligibility else [],
            home_location=home_location,
        )


def _job_skill_sets(job: Job) -> tuple[set[str], set[str], set[str]]:
    required = set(canonical_skills(job.required_skills))
    preferred = set(canonical_skills(job.preferred_skills))
    technologies = set(canonical_skills(job.technologies))
    return required, preferred, technologies


def check_eligibility(job: Job, candidate: CandidateProfile) -> list[str]:
    """Hard rules. A non-empty result means the job can never be recommended."""
    blocking: list[str] = []

    if candidate.requires_sponsorship and job.sponsorship_available is False:
        blocking.append("This employer does not sponsor work visas.")
    if job.citizenship_required and candidate.work_authorization not in {
        WorkAuthorization.CITIZEN.value
    }:
        blocking.append("The role requires citizenship you have not indicated.")

    required_clearance = job.requires_clearance
    if required_clearance and required_clearance != "none":
        held = CLEARANCE_ORDER.get(candidate.security_clearance, 0)
        needed = CLEARANCE_ORDER.get(required_clearance, 0)
        if held < needed:
            blocking.append(
                f"Requires a {required_clearance.replace('_', ' ')} clearance you do not hold."
            )

    if (
        candidate.authorized_countries
        and job.country
        and job.country.upper() not in {code.upper() for code in candidate.authorized_countries}
    ):
        blocking.append(f"You are not authorised to work in {job.country}.")

    if candidate.excluded_companies and job.company is not None:
        if normalize(job.company.name) in candidate.excluded_companies:
            blocking.append(f"{job.company.name} is on your excluded-companies list.")

    normalized_title = normalize(job.title)
    for excluded in candidate.excluded_titles:
        if normalize(excluded) and normalize(excluded) in normalized_title:
            blocking.append(f'Title contains your excluded term "{excluded}".')
            break

    if candidate.minimum_salary and job.salary_max and job.salary_max < candidate.minimum_salary:
        blocking.append(
            f"Top of the posted range (${job.salary_max:,}) is below your "
            f"${candidate.minimum_salary:,} minimum."
        )

    if candidate.max_days_since_posted and job.date_posted:
        age_days = (date.today() - job.date_posted).days
        if age_days > candidate.max_days_since_posted:
            blocking.append(
                f"Posted {age_days} days ago, beyond your {candidate.max_days_since_posted}-day limit."
            )

    if candidate.work_arrangements and job.work_arrangement:
        if job.work_arrangement not in candidate.work_arrangements:
            blocking.append(
                f"Work setup ({job.work_arrangement}) is not one you selected."
            )

    return blocking


def _score_skills(
    job_required: set[str], job_preferred: set[str], candidate_skills: set[str]
) -> tuple[float, list[Qualification], str]:
    quals: list[Qualification] = []
    if not job_required and not job_preferred:
        return 0.0, quals, "no-signal"

    matched_required = sorted(job_required & candidate_skills)
    missing_required = sorted(job_required - candidate_skills)
    matched_preferred = sorted(job_preferred & candidate_skills)
    missing_preferred = sorted(job_preferred - candidate_skills)

    for skill in matched_required:
        quals.append(
            Qualification(
                kind=MatchQualificationKind.STRONG,
                category="skills",
                label=skill,
                detail="Required skill found on your resume",
            )
        )
    for skill in matched_preferred:
        quals.append(
            Qualification(
                kind=MatchQualificationKind.PARTIAL,
                category="skills",
                label=skill,
                detail="Nice-to-have skill you already have",
            )
        )
    for skill in missing_required:
        quals.append(
            Qualification(
                kind=MatchQualificationKind.MISSING,
                category="skills",
                label=skill,
                detail="Required skill not found on your resume",
            )
        )
    for skill in missing_preferred:
        quals.append(
            Qualification(
                kind=MatchQualificationKind.MISSING,
                category="skills",
                label=skill,
                detail="Nice-to-have skill you do not list",
            )
        )

    required_ratio = overlap_ratio(job_required, candidate_skills)
    preferred_ratio = overlap_ratio(job_preferred, candidate_skills) if job_preferred else None
    if preferred_ratio is None:
        score = required_ratio
    else:
        score = 0.75 * required_ratio + 0.25 * preferred_ratio
    detail = f"{len(matched_required)}/{len(job_required) or 0} required skills matched"
    return score, quals, detail


def _score_technologies(
    job_techs: set[str], candidate_techs: set[str]
) -> tuple[float, list[Qualification], str]:
    if not job_techs:
        return 0.0, [], "no-signal"
    matched = sorted(job_techs & candidate_techs)
    missing = sorted(job_techs - candidate_techs)
    quals = [
        Qualification(
            kind=MatchQualificationKind.STRONG,
            category="technologies",
            label=tech,
            detail="Technology you have worked with",
        )
        for tech in matched
    ]
    quals += [
        Qualification(
            kind=MatchQualificationKind.MISSING,
            category="technologies",
            label=tech,
            detail="Technology in the posting you do not list",
        )
        for tech in missing
    ]
    return (
        overlap_ratio(job_techs, candidate_techs),
        quals,
        f"{len(matched)}/{len(job_techs)} technologies matched",
    )


def _title_similarity(job_title: str, candidate_titles: Iterable[str]) -> float:
    job_tokens = tokenize(normalize_title(job_title))
    best = 0.0
    for title in candidate_titles:
        if not title:
            continue
        candidate_tokens = tokenize(normalize_title(title))
        best = max(best, jaccard(job_tokens, candidate_tokens))
    return best


def _score_title(job: Job, candidate: CandidateProfile) -> tuple[float, list[Qualification], str]:
    against = [*candidate.desired_titles, *candidate.titles]
    if not against:
        return 0.0, [], "no-signal"
    score = _title_similarity(job.title, against)
    if score >= 0.6:
        kind, detail = MatchQualificationKind.STRONG, "Closely matches your target titles"
    elif score >= 0.3:
        kind, detail = MatchQualificationKind.PARTIAL, "Related to your target titles"
    else:
        kind, detail = MatchQualificationKind.MISSING, "Differs from your target titles"
    qual = Qualification(
        kind=kind, category="title", label=job.title, detail=detail
    )
    return score, [qual], f"title similarity {score:.0%}"


def _score_experience(job: Job, candidate: CandidateProfile) -> tuple[float, list[Qualification], str]:
    quals: list[Qualification] = []
    scores: list[float] = []
    detail_parts: list[str] = []

    if job.min_years_experience is not None and candidate.years_of_experience is not None:
        needed = float(job.min_years_experience)
        have = candidate.years_of_experience
        if have >= needed:
            scores.append(1.0)
            quals.append(
                Qualification(
                    kind=MatchQualificationKind.STRONG,
                    category="experience",
                    label=f"{have:.0f} years experience",
                    detail=f"Meets the {needed:.0f}-year requirement",
                )
            )
        elif needed > 0 and have >= needed - 1:
            scores.append(0.6)
            quals.append(
                Qualification(
                    kind=MatchQualificationKind.PARTIAL,
                    category="experience",
                    label=f"{have:.0f} of {needed:.0f} years",
                    detail="Just under the stated requirement",
                )
            )
        else:
            scores.append(max(0.0, have / needed) if needed else 0.0)
            quals.append(
                Qualification(
                    kind=MatchQualificationKind.MISSING,
                    category="experience",
                    label=f"{needed:.0f} years required",
                    detail=f"You have about {have:.0f}",
                )
            )
        detail_parts.append(f"{have:.0f}/{needed:.0f} years")

    if job.experience_level and candidate.experience_levels:
        job_rank = EXPERIENCE_LEVEL_ORDER.get(job.experience_level)
        wanted = [
            EXPERIENCE_LEVEL_ORDER[level]
            for level in candidate.experience_levels
            if level in EXPERIENCE_LEVEL_ORDER
        ]
        if job_rank is not None and wanted:
            distance = min(abs(job_rank - rank) for rank in wanted)
            level_score = max(0.0, 1.0 - 0.4 * distance)
            scores.append(level_score)
            if distance == 0:
                kind, text = MatchQualificationKind.STRONG, "Matches your target level"
            elif distance == 1:
                kind, text = MatchQualificationKind.PARTIAL, "One level from your target"
            else:
                kind, text = MatchQualificationKind.MISSING, "Outside your target levels"
            quals.append(
                Qualification(
                    kind=kind,
                    category="experience",
                    label=job.experience_level.replace("_", " ").title(),
                    detail=text,
                )
            )
            detail_parts.append(f"level distance {distance}")

    if not scores:
        return 0.0, quals, "no-signal"
    return sum(scores) / len(scores), quals, ", ".join(detail_parts)


def _score_location(job: Job, candidate: CandidateProfile) -> tuple[float, list[Qualification], str]:
    arrangement = job.work_arrangement
    if arrangement == WorkArrangement.REMOTE.value:
        return (
            1.0,
            [
                Qualification(
                    kind=MatchQualificationKind.STRONG,
                    category="location",
                    label="Remote",
                    detail="Fully remote role",
                )
            ],
            "remote",
        )

    if not candidate.preferred_locations and not candidate.home_location:
        return 0.0, [], "no-signal"

    job_location = normalize(job.location or " ".join(filter(None, [job.city, job.region])))
    if not job_location:
        return 0.0, [], "no-signal"

    references = [*candidate.preferred_locations]
    if candidate.home_location:
        references.append(candidate.home_location)
    best = max((jaccard(tokenize(job_location), tokenize(ref)) for ref in references), default=0.0)

    label = job.location or job_location
    if best >= 0.5:
        kind, detail, score = (
            MatchQualificationKind.STRONG,
            "In a location you selected",
            1.0,
        )
    elif best > 0:
        kind, detail, score = (
            MatchQualificationKind.PARTIAL,
            "Near a location you selected",
            0.6,
        )
    elif candidate.willing_to_relocate:
        kind, detail, score = (
            MatchQualificationKind.PARTIAL,
            "Outside your locations, but you are open to relocating",
            0.4,
        )
    else:
        kind, detail, score = (
            MatchQualificationKind.MISSING,
            "Outside the locations you selected",
            0.0,
        )
    qual = Qualification(kind=kind, category="location", label=label, detail=detail)
    return score, [qual], f"location overlap {best:.0%}"


def _score_salary(job: Job, candidate: CandidateProfile) -> tuple[float, list[Qualification], str]:
    if candidate.minimum_salary is None:
        return 0.0, [], "no-signal"
    if job.salary_min is None and job.salary_max is None:
        return (
            0.0,
            [
                Qualification(
                    kind=MatchQualificationKind.PARTIAL,
                    category="salary",
                    label="Salary not published",
                    detail="This posting does not list compensation",
                )
            ],
            "no-signal",
        )
    top = job.salary_max or job.salary_min or 0
    bottom = job.salary_min or job.salary_max or 0
    minimum = candidate.minimum_salary
    if bottom >= minimum:
        kind, detail, score = (
            MatchQualificationKind.STRONG,
            f"Range starts at or above your ${minimum:,} minimum",
            1.0,
        )
    elif top >= minimum:
        kind, detail, score = (
            MatchQualificationKind.PARTIAL,
            f"Top of the range clears your ${minimum:,} minimum",
            0.6,
        )
    else:
        kind, detail, score = (
            MatchQualificationKind.MISSING,
            f"Below your ${minimum:,} minimum",
            0.0,
        )
    label = (
        f"${bottom:,} - ${top:,}" if bottom and top and bottom != top else f"${top or bottom:,}"
    )
    return score, [Qualification(kind=kind, category="salary", label=label, detail=detail)], detail


def _summarize(score: int, strong: int, missing: int, eligible: bool) -> str:
    if not eligible:
        return "Not eligible — a hard requirement rules this role out."
    if score >= 80:
        return f"Strong match: {strong} qualifications line up."
    if score >= 60:
        return f"Good match with {missing} gap{'s' if missing != 1 else ''}."
    if score >= 40:
        return f"Partial match — {missing} notable gap{'s' if missing != 1 else ''}."
    return "Weak match against your profile and preferences."


def score_job(job: Job, candidate: CandidateProfile) -> MatchResult:
    """Score one job for one candidate and explain the result."""
    blocking = check_eligibility(job, candidate)
    required, preferred, technologies = _job_skill_sets(job)

    raw_components: list[tuple[str, float, list[Qualification], str]] = [
        ("skills", *_score_skills(required, preferred, candidate.skills)),
        ("technologies", *_score_technologies(technologies, candidate.skills)),
        ("title", *_score_title(job, candidate)),
        ("experience", *_score_experience(job, candidate)),
        ("location", *_score_location(job, candidate)),
        ("salary", *_score_salary(job, candidate)),
    ]

    components: list[ComponentScore] = []
    quals: list[Qualification] = []
    weighted_total = 0.0
    weight_total = 0.0
    for name, score, component_quals, detail in raw_components:
        quals.extend(component_quals)
        weight = WEIGHTS[name]
        applies = detail != "no-signal"
        components.append(
            ComponentScore(name=name, score=round(score, 4), weight=weight if applies else 0.0, detail=detail)
        )
        if applies:
            weighted_total += score * weight
            weight_total += weight

    percent = int(round(100 * weighted_total / weight_total)) if weight_total else 0
    strong = [qual for qual in quals if qual.kind == MatchQualificationKind.STRONG]
    partial = [qual for qual in quals if qual.kind == MatchQualificationKind.PARTIAL]
    missing = [qual for qual in quals if qual.kind == MatchQualificationKind.MISSING]

    eligible = not blocking
    if not eligible:
        percent = 0

    return MatchResult(
        score=percent,
        eligible=eligible,
        blocking_reasons=blocking,
        strong=strong,
        partial=partial,
        missing=missing,
        components=components,
        summary=_summarize(percent, len(strong), len(missing), eligible),
    )


def score_jobs(
    jobs: Iterable[Job], candidate: CandidateProfile
) -> list[tuple[Job, MatchResult]]:
    """Score many jobs, best first, dropping the ineligible ones."""
    scored = [(job, score_job(job, candidate)) for job in jobs]
    eligible = [pair for pair in scored if pair[1].eligible]
    # Best score first; freshest posting breaks ties.
    eligible.sort(
        key=lambda pair: (
            -pair[1].score,
            -(pair[0].date_posted or date.min).toordinal(),
        )
    )
    return eligible


def result_to_json(result: MatchResult) -> dict[str, Any]:
    return result.model_dump(mode="json")
