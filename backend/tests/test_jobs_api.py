"""Features 4 and 10: browsing jobs and the job-details page."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.job import Company
from app.models.user import User
from tests.conftest import make_job, make_resume


def test_the_job_list_shows_only_open_listings_by_default(
    client: TestClient, db: Session, company: Company, user_headers: dict[str, str]
) -> None:
    make_job(db, company, title="Open role")
    make_job(db, company, title="Closed role", status=JobStatus.CLOSED.value)

    body = client.get("/api/v1/jobs", headers=user_headers).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Open role"
    assert body["items"][0]["company"]["name"] == "Acme Corp"


def test_duplicates_are_hidden_from_the_job_list(
    client: TestClient, db: Session, company: Company, user_headers: dict[str, str]
) -> None:
    original = make_job(db, company, title="Senior Backend Engineer")
    copy = make_job(db, company, title="Sr Backend Engineer")
    copy.duplicate_of_id = original.id
    copy.status = JobStatus.DUPLICATE.value
    db.flush()

    body = client.get("/api/v1/jobs", headers=user_headers).json()
    assert body["total"] == 1


def test_the_job_list_filters(
    client: TestClient, db: Session, company: Company, user_headers: dict[str, str]
) -> None:
    make_job(db, company, title="Remote Python Engineer", work_arrangement="remote")
    make_job(
        db, company, title="Onsite Java Engineer", work_arrangement="onsite", salary_max=90_000
    )

    remote = client.get("/api/v1/jobs?work_arrangement=remote", headers=user_headers).json()
    assert remote["total"] == 1

    searched = client.get("/api/v1/jobs?q=java", headers=user_headers).json()
    assert searched["total"] == 1

    well_paid = client.get("/api/v1/jobs?min_salary=150000", headers=user_headers).json()
    assert well_paid["total"] == 1
    assert well_paid["items"][0]["title"] == "Remote Python Engineer"


def test_the_job_list_paginates(
    client: TestClient, db: Session, company: Company, user_headers: dict[str, str]
) -> None:
    for index in range(7):
        make_job(db, company, title=f"Engineer {index}")

    first = client.get("/api/v1/jobs?limit=5&offset=0", headers=user_headers).json()
    assert first["total"] == 7
    assert len(first["items"]) == 5

    second = client.get("/api/v1/jobs?limit=5&offset=5", headers=user_headers).json()
    assert len(second["items"]) == 2


def test_the_details_page_carries_the_full_record(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    job = make_job(db, company, work_arrangement="hybrid", street_address="500 Market St")
    make_resume(db, user)
    db.refresh(user)

    response = client.get(f"/api/v1/jobs/{job.id}", headers=user_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["job"]["description"]
    assert body["job"]["description_snapshot"] == job.description_snapshot
    assert body["job"]["street_address"] == "500 Market St"
    assert body["job"]["source_url"] == job.source_url
    assert body["job"]["company"]["name"] == "Acme Corp"
    assert body["job"]["last_verified_at"] is not None


def test_the_details_page_explains_the_match(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    make_resume(db, user)
    db.refresh(user)

    match = client.get(f"/api/v1/jobs/{job.id}", headers=user_headers).json()["match"]
    assert match["eligible"] is True
    assert match["score"] > 0
    assert match["summary"]
    assert any(item["category"] == "skills" for item in match["strong"])
    assert {item["name"] for item in match["components"]} == {
        "skills",
        "technologies",
        "title",
        "experience",
        "location",
        "salary",
    }


def test_the_details_page_reuses_the_batch_explanation(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    card = batch["recommendations"][0]

    detail = client.get(f"/api/v1/jobs/{job.id}", headers=user_headers).json()
    assert detail["recommendation_id"] == card["id"]
    assert detail["match"]["score"] == card["match_score"]


def test_the_details_page_flags_a_saved_job(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    client.post(
        f"/api/v1/batches/recommendations/{batch['recommendations'][0]['id']}/save",
        headers=user_headers,
    )

    detail = client.get(f"/api/v1/jobs/{job.id}", headers=user_headers).json()
    assert detail["is_saved"] is True


def test_the_details_page_flags_an_existing_application(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    client.post(
        f"/api/v1/batches/recommendations/{batch['recommendations'][0]['id']}/apply",
        headers=user_headers,
        json={},
    )

    detail = client.get(f"/api/v1/jobs/{job.id}", headers=user_headers).json()
    assert detail["already_applied"] is True
    assert detail["recommendation_status"] == "applied"


def test_an_unknown_job_returns_404(client: TestClient, user_headers: dict[str, str]) -> None:
    import uuid

    response = client.get(f"/api/v1/jobs/{uuid.uuid4()}", headers=user_headers)
    assert response.status_code == 404


def test_job_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/jobs").status_code == 401
