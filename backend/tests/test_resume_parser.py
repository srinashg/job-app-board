"""Feature 2: resume text extraction and structured parsing."""

from __future__ import annotations

import pytest

from app.services.resume_parser import (
    ResumeParseError,
    extract_text,
    parse_resume_text,
    split_sections,
)

SAMPLE = """Jane Q. Doe
San Francisco, CA
jane.doe@example.com | (415) 555-0134

SUMMARY
Backend engineer with 7 years of experience building Python services.

TECHNICAL SKILLS
Languages: Python, TypeScript, Go
Cloud: AWS, Docker, Kubernetes
Databases: PostgreSQL, Redis

PROFESSIONAL EXPERIENCE
Senior Software Engineer | Acme Corp
Jan 2021 - Present
- Built FastAPI services handling 2M requests/day
- Mentored four engineers

Software Engineer | Globex
2018 - 2021
- Migrated a monolith to microservices on Kubernetes

EDUCATION
University of California, Berkeley
B.S. in Computer Science, 2018
GPA: 3.8

CERTIFICATIONS
AWS Certified Solutions Architect - Amazon Web Services, 2022
"""


@pytest.fixture(scope="module")
def parsed():
    return parse_resume_text(SAMPLE)


def test_sections_are_recognised_under_their_aliases() -> None:
    sections = split_sections(SAMPLE)
    assert set(sections) >= {"header", "summary", "skills", "experience", "education", "certifications"}


def test_contact_details_are_extracted(parsed) -> None:
    assert parsed.full_name == "Jane Q. Doe"
    assert parsed.email == "jane.doe@example.com"
    assert parsed.phone == "(415) 555-0134"
    assert parsed.location == "San Francisco, CA"


def test_skills_are_canonicalised_and_deduplicated(parsed) -> None:
    assert "python" in parsed.skills
    assert "postgresql" in parsed.skills
    assert "kubernetes" in parsed.skills
    # FastAPI is only mentioned in a bullet, not the skills block.
    assert "fastapi" in parsed.skills
    assert len(parsed.skills) == len(set(parsed.skills))


def test_experience_entries_keep_title_company_and_dates(parsed) -> None:
    assert len(parsed.experience) == 2
    current = parsed.experience[0]
    assert current["title"] == "Senior Software Engineer"
    assert current["company"] == "Acme Corp"
    assert current["start_date"] == "Jan 2021"
    assert current["is_current"] is True

    previous = parsed.experience[1]
    # The company name must not be swallowed into the date range.
    assert previous["start_date"] == "2018"
    assert previous["company"] == "Globex"
    assert previous["is_current"] is False


def test_education_and_certifications(parsed) -> None:
    assert parsed.education[0]["institution"] == "University of California, Berkeley"
    assert parsed.education[0]["end_date"] == "2018"
    assert parsed.education[0]["gpa"] == "3.8"
    assert parsed.certifications[0]["name"] == "AWS Certified Solutions Architect"


def test_job_titles_and_years_of_experience(parsed) -> None:
    assert parsed.job_titles == ["Senior Software Engineer", "Software Engineer"]
    # The stated "7 years of experience" wins over the summed date ranges.
    assert parsed.years_of_experience == 7.0


def test_years_fall_back_to_summed_date_ranges() -> None:
    without_summary = SAMPLE.replace(
        "Backend engineer with 7 years of experience building Python services.", "Backend engineer."
    )
    parsed = parse_resume_text(without_summary)
    assert parsed.years_of_experience is not None
    assert parsed.years_of_experience > 0


def test_plain_text_extraction_round_trips() -> None:
    text = extract_text(SAMPLE.encode("utf-8"), "text/plain", "resume.txt")
    assert "Jane Q. Doe" in text


def test_unsupported_format_is_rejected() -> None:
    with pytest.raises(ResumeParseError):
        extract_text(b"binary", "image/png", "resume.png")


def test_corrupt_pdf_raises_a_readable_error() -> None:
    with pytest.raises(ResumeParseError):
        extract_text(b"not really a pdf", "application/pdf", "resume.pdf")


def test_parsing_an_empty_resume_yields_empty_fields() -> None:
    parsed = parse_resume_text("   \n\n  ")
    assert parsed.skills == []
    assert parsed.experience == []
    assert parsed.full_name is None
