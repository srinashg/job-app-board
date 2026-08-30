"""Feature 6: eligibility gates and weighted match scoring."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.enums import MatchQualificationKind
from app.models.job import Company
from app.models.user import User
from app.services.matching import CandidateProfile, score_job
from app.services.recommendations import build_candidate_profile
from tests.conftest import make_job, make_resume


def profile_for(db: Session, user: User) -> CandidateProfile:
    make_resume(db, user)
    db.refresh(user)
    return build_candidate_profile(db, user)


def test_a_well_aligned_job_scores_highly(db: Session, user: User, company: Company) -> None:
    candidate = profile_for(db, user)
    job = make_job(db, company)
    result = score_job(job, candidate)

    assert result.eligible is True
    assert result.score >= 80
    assert any(qual.label == "python" for qual in result.strong)
    assert "Strong match" in result.summary


def test_missing_required_skills_appear_as_gaps(db: Session, user: User, company: Company) -> None:
    candidate = profile_for(db, user)
    job = make_job(
        db,
        company,
        required_skills=["rust", "kafka", "terraform"],
        technologies=["rust", "kafka"],
    )
    result = score_job(job, candidate)

    missing = {qual.label for qual in result.missing}
    assert {"rust", "kafka", "terraform"} <= missing
    assert result.score < 60


def test_sponsorship_requirement_blocks_the_job(db: Session, user: User, company: Company) -> None:
    user.eligibility.requires_sponsorship = True
    db.flush()
    candidate = profile_for(db, user)
    job = make_job(db, company, sponsorship_available=False)
    result = score_job(job, candidate)

    assert result.eligible is False
    assert result.score == 0
    assert any("sponsor" in reason.lower() for reason in result.blocking_reasons)


def test_clearance_requirement_blocks_when_the_user_has_none(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)
    job = make_job(db, company, requires_clearance="top_secret")
    result = score_job(job, candidate)

    assert result.eligible is False
    assert any("clearance" in reason.lower() for reason in result.blocking_reasons)


def test_holding_a_higher_clearance_satisfies_a_lower_requirement(
    db: Session, user: User, company: Company
) -> None:
    user.eligibility.security_clearance = "top_secret"
    db.flush()
    candidate = profile_for(db, user)
    job = make_job(db, company, requires_clearance="secret")
    assert score_job(job, candidate).eligible is True


def test_citizenship_requirement_blocks_a_visa_holder(
    db: Session, user: User, company: Company
) -> None:
    user.eligibility.work_authorization = "visa_holder"
    db.flush()
    candidate = profile_for(db, user)
    job = make_job(db, company, citizenship_required=True)
    assert score_job(job, candidate).eligible is False


def test_salary_below_the_minimum_blocks_the_job(
    db: Session, user: User, company: Company
) -> None:
    user.preferences.minimum_salary = 250_000
    db.flush()
    candidate = profile_for(db, user)
    job = make_job(db, company, salary_min=100_000, salary_max=130_000)
    result = score_job(job, candidate)

    assert result.eligible is False
    assert any("minimum" in reason for reason in result.blocking_reasons)


def test_excluded_company_blocks_the_job(db: Session, user: User, company: Company) -> None:
    user.preferences.excluded_companies = ["Acme Corp"]
    db.flush()
    candidate = profile_for(db, user)
    result = score_job(make_job(db, company), candidate)

    assert result.eligible is False
    assert any("excluded-companies" in reason for reason in result.blocking_reasons)


def test_excluded_title_term_blocks_the_job(db: Session, user: User, company: Company) -> None:
    user.preferences.excluded_titles = ["manager"]
    db.flush()
    candidate = profile_for(db, user)
    result = score_job(make_job(db, company, title="Engineering Manager"), candidate)
    assert result.eligible is False


def test_a_work_setup_the_user_did_not_pick_is_blocked(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)  # prefers remote and hybrid
    result = score_job(make_job(db, company, work_arrangement="onsite"), candidate)

    assert result.eligible is False
    assert any("Work setup" in reason for reason in result.blocking_reasons)


def test_a_stale_posting_is_blocked_by_the_date_filter(
    db: Session, user: User, company: Company
) -> None:
    user.preferences.max_days_since_posted = 7
    db.flush()
    candidate = profile_for(db, user)
    job = make_job(db, company, date_posted=date.today() - timedelta(days=45))
    result = score_job(job, candidate)

    assert result.eligible is False
    assert any("days ago" in reason for reason in result.blocking_reasons)


def test_experience_shortfall_shows_as_a_gap_not_a_block(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)  # 6 years
    job = make_job(db, company, min_years_experience=12)
    result = score_job(job, candidate)

    assert result.eligible is True
    assert any(
        qual.category == "experience" and qual.kind == MatchQualificationKind.MISSING
        for qual in result.missing
    )


def test_remote_roles_always_score_full_marks_on_location(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)
    result = score_job(make_job(db, company, work_arrangement="remote"), candidate)
    location = next(item for item in result.components if item.name == "location")
    assert location.score == 1.0


def test_components_without_signal_carry_no_weight(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)
    job = make_job(db, company, salary_min=None, salary_max=None)
    user.preferences.minimum_salary = None
    db.flush()
    result = score_job(job, candidate)

    salary = next(item for item in result.components if item.name == "salary")
    assert salary.weight == 0.0
    assert salary.detail == "no-signal"


def test_the_score_is_traceable_to_its_qualifications(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)
    result = score_job(make_job(db, company), candidate)

    assert result.strong or result.partial or result.missing
    for qual in [*result.strong, *result.partial, *result.missing]:
        assert qual.category
        assert qual.label


def test_a_term_is_listed_once_across_signals(
    db: Session, user: User, company: Company
) -> None:
    """A skill that is both a requirement and a listed technology shows once."""
    candidate = profile_for(db, user)
    job = make_job(
        db,
        company,
        required_skills=["python", "postgresql"],
        technologies=["python", "postgresql"],
    )
    result = score_job(job, candidate)

    strong_labels = [qual.label for qual in result.strong]
    assert strong_labels.count("python") == 1
    assert strong_labels.count("postgresql") == 1


def test_a_gap_is_listed_once_and_never_alongside_a_strength(
    db: Session, user: User, company: Company
) -> None:
    candidate = profile_for(db, user)
    job = make_job(
        db,
        company,
        required_skills=["python", "kafka"],
        technologies=["python", "kafka"],
    )
    result = score_job(job, candidate)

    missing_labels = [qual.label for qual in result.missing]
    assert missing_labels.count("kafka") == 1
    assert "python" not in missing_labels
    assert "python" in [qual.label for qual in result.strong]


def test_a_term_lands_in_exactly_one_bucket(
    db: Session, user: User, company: Company
) -> None:
    """A nice-to-have the user has, also listed as a technology, is not both."""
    candidate = profile_for(db, user)
    job = make_job(
        db,
        company,
        required_skills=["python"],
        technologies=["python", "docker", "fastapi"],
    )
    result = score_job(job, candidate)

    buckets = {
        "strong": {qual.label for qual in result.strong},
        "partial": {qual.label for qual in result.partial},
        "missing": {qual.label for qual in result.missing},
    }
    assert not buckets["strong"] & buckets["partial"]
    assert not buckets["strong"] & buckets["missing"]
    assert not buckets["partial"] & buckets["missing"]
    # A skill the user has is a strength, never a nice-to-have gap.
    assert "docker" in buckets["strong"]
