"""Feature 9: the preference filter panel and its effect on recommendations."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.job import Company
from app.models.user import User
from tests.conftest import make_job, make_resume

ALL_FILTERS = {
    "work_arrangements": ["remote", "hybrid"],
    "preferred_locations": ["Austin, TX", "Remote"],
    "location_radius_miles": 40,
    "desired_titles": ["Backend Engineer"],
    "excluded_titles": ["Manager"],
    "technologies": ["python", "kubernetes"],
    "industries": ["fintech"],
    "excluded_companies": ["Globex"],
    "experience_levels": ["senior", "lead"],
    "minimum_salary": 140000,
    "max_days_since_posted": 14,
    "match_threshold": 55,
}


def test_every_documented_filter_round_trips(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.put("/api/v1/me/preferences", headers=user_headers, json=ALL_FILTERS)
    assert response.status_code == 200, response.text

    stored = client.get("/api/v1/me/preferences", headers=user_headers).json()
    for field, value in ALL_FILTERS.items():
        assert stored[field] == value, field


def test_a_partial_update_leaves_other_filters_alone(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    client.put("/api/v1/me/preferences", headers=user_headers, json=ALL_FILTERS)
    client.put("/api/v1/me/preferences", headers=user_headers, json={"match_threshold": 70})

    stored = client.get("/api/v1/me/preferences", headers=user_headers).json()
    assert stored["match_threshold"] == 70
    assert stored["technologies"] == ["python", "kubernetes"]


def test_invalid_filter_values_are_rejected(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    for payload in (
        {"match_threshold": 150},
        {"work_arrangements": ["underwater"]},
        {"experience_levels": ["wizard"]},
        {"minimum_salary": -1},
        {"max_days_since_posted": 0},
    ):
        response = client.put("/api/v1/me/preferences", headers=user_headers, json=payload)
        assert response.status_code == 422, payload


def test_the_work_setup_filter_narrows_recommendations(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, title="Remote role", work_arrangement="remote")
    make_job(db, company, title="Onsite role", work_arrangement="onsite")
    db.refresh(user)

    client.put(
        "/api/v1/me/preferences", headers=user_headers, json={"work_arrangements": ["remote"]}
    )
    preview = client.get("/api/v1/batches/preview", headers=user_headers).json()
    assert [item["job"]["title"] for item in preview] == ["Remote role"]


def test_the_excluded_company_filter_removes_its_jobs(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company)
    db.refresh(user)

    assert client.get("/api/v1/batches/preview", headers=user_headers).json()

    client.put(
        "/api/v1/me/preferences", headers=user_headers, json={"excluded_companies": ["Acme Corp"]}
    )
    assert client.get("/api/v1/batches/preview", headers=user_headers).json() == []


def test_the_date_posted_filter_drops_old_listings(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, title="Fresh", date_posted=date.today() - timedelta(days=2))
    make_job(db, company, title="Ancient", date_posted=date.today() - timedelta(days=90))
    db.refresh(user)

    client.put("/api/v1/me/preferences", headers=user_headers, json={"max_days_since_posted": 7})
    preview = client.get("/api/v1/batches/preview", headers=user_headers).json()
    assert [item["job"]["title"] for item in preview] == ["Fresh"]


def test_the_salary_filter_drops_underpaying_roles(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, title="Well paid", salary_min=180_000, salary_max=220_000)
    make_job(db, company, title="Underpaid", salary_min=80_000, salary_max=95_000)
    db.refresh(user)

    client.put("/api/v1/me/preferences", headers=user_headers, json={"minimum_salary": 150_000})
    preview = client.get("/api/v1/batches/preview", headers=user_headers).json()
    assert [item["job"]["title"] for item in preview] == ["Well paid"]


def test_the_excluded_title_filter_removes_matching_titles(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, title="Backend Engineer")
    make_job(db, company, title="Engineering Manager")
    db.refresh(user)

    client.put("/api/v1/me/preferences", headers=user_headers, json={"excluded_titles": ["Manager"]})
    preview = client.get("/api/v1/batches/preview", headers=user_headers).json()
    assert [item["job"]["title"] for item in preview] == ["Backend Engineer"]


def test_eligibility_rules_round_trip(client: TestClient, user_headers: dict[str, str]) -> None:
    payload = {
        "work_authorization": "visa_holder",
        "requires_sponsorship": True,
        "security_clearance": "secret",
        "willing_to_relocate": True,
        "authorized_countries": ["US", "CA"],
        "minimum_salary": 130000,
        "earliest_start_date": "2026-10-01",
        "total_years_experience": 8.5,
    }
    response = client.put("/api/v1/me/eligibility", headers=user_headers, json=payload)
    assert response.status_code == 200

    stored = client.get("/api/v1/me/eligibility", headers=user_headers).json()
    for field, value in payload.items():
        assert stored[field] == value, field


def test_invalid_eligibility_values_are_rejected(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    for payload in (
        {"work_authorization": "martian"},
        {"security_clearance": "cosmic"},
        {"total_years_experience": 200},
    ):
        assert (
            client.put("/api/v1/me/eligibility", headers=user_headers, json=payload).status_code
            == 422
        )
