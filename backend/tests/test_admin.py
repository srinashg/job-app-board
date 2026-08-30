"""Feature 14: the /admin/jobs moderation surface."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import JobStatus, RecommendationStatus
from app.models.job import Company, Job
from app.models.recommendation import Recommendation
from app.models.user import User
from tests.conftest import make_job, make_resume


def test_admin_endpoints_reject_ordinary_users(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    assert client.get("/api/v1/admin/jobs", headers=user_headers).status_code == 403
    assert client.get("/api/v1/admin/stats", headers=user_headers).status_code == 403
    assert client.post(
        "/api/v1/admin/blacklists",
        headers=user_headers,
        json={"scope": "company", "value": "acme"},
    ).status_code == 403


def test_the_jobs_table_lists_listings_with_moderation_state(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    make_job(db, company, title="Senior Backend Engineer")
    make_job(db, company, title="Data Analyst", status=JobStatus.CLOSED.value)

    response = client.get("/api/v1/admin/jobs", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    row = body["items"][0]
    assert row["company_name"] == "Acme Corp"
    assert row["source_url"]
    assert "recommendation_count" in row


def test_the_jobs_table_filters_by_status_and_search(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    make_job(db, company, title="Senior Backend Engineer")
    make_job(db, company, title="Data Analyst", status=JobStatus.CLOSED.value)

    closed = client.get("/api/v1/admin/jobs?status=closed", headers=admin_headers).json()
    assert closed["total"] == 1
    assert closed["items"][0]["title"] == "Data Analyst"

    searched = client.get("/api/v1/admin/jobs?q=backend", headers=admin_headers).json()
    assert searched["total"] == 1


def test_disabling_a_job_withdraws_it_from_open_batches(
    client: TestClient, db: Session, user: User, company: Company, admin_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)

    from app.services.recommendations import ensure_active_batch

    ensure_active_batch(db, user)

    response = client.post(
        "/api/v1/admin/jobs/actions",
        headers=admin_headers,
        json={"job_ids": [str(job.id)], "action": "disable", "notes": "Broken link"},
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 1

    db.refresh(job)
    assert job.status == JobStatus.DISABLED.value
    assert job.moderation_notes == "Broken link"

    from sqlalchemy import select

    recommendation = db.execute(
        select(Recommendation).where(Recommendation.job_id == job.id)
    ).scalar_one()
    assert recommendation.status == RecommendationStatus.CLOSED.value


def test_each_moderation_action_sets_its_status(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    for action, expected in [
        ("mark_stale", JobStatus.STALE.value),
        ("mark_scam", JobStatus.SCAM.value),
        ("mark_closed", JobStatus.CLOSED.value),
        ("disable", JobStatus.DISABLED.value),
        ("enable", JobStatus.ACTIVE.value),
    ]:
        job = make_job(db, company, title=f"Role for {action}")
        response = client.post(
            "/api/v1/admin/jobs/actions",
            headers=admin_headers,
            json={"job_ids": [str(job.id)], "action": action},
        )
        assert response.status_code == 200, response.text
        db.refresh(job)
        assert job.status == expected


def test_marking_a_duplicate_requires_and_records_the_original(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    original = make_job(db, company, title="Senior Backend Engineer")
    copy = make_job(db, company, title="Sr. Backend Engineer")

    missing_target = client.post(
        "/api/v1/admin/jobs/actions",
        headers=admin_headers,
        json={"job_ids": [str(copy.id)], "action": "mark_duplicate"},
    )
    assert missing_target.status_code == 400

    response = client.post(
        "/api/v1/admin/jobs/actions",
        headers=admin_headers,
        json={
            "job_ids": [str(copy.id)],
            "action": "mark_duplicate",
            "duplicate_of_id": str(original.id),
        },
    )
    assert response.status_code == 200
    db.refresh(copy)
    assert copy.status == JobStatus.DUPLICATE.value
    assert copy.duplicate_of_id == original.id


def test_a_job_cannot_be_a_duplicate_of_itself(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    response = client.post(
        "/api/v1/admin/jobs/actions",
        headers=admin_headers,
        json={
            "job_ids": [str(job.id)],
            "action": "mark_duplicate",
            "duplicate_of_id": str(job.id),
        },
    )
    assert response.status_code == 400


def test_an_unknown_action_is_rejected(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    response = client.post(
        "/api/v1/admin/jobs/actions",
        headers=admin_headers,
        json={"job_ids": [str(job.id)], "action": "nuke"},
    )
    assert response.status_code == 400


def test_blacklisting_a_company_disables_its_jobs(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    response = client.post(
        "/api/v1/admin/blacklists",
        headers=admin_headers,
        json={"scope": "company", "value": "Acme Corp", "reason": "Repeated scam postings"},
    )
    assert response.status_code == 201
    assert response.json()["value"] == "acme-corp"

    db.refresh(company)
    db.refresh(job)
    assert company.is_blacklisted is True
    assert job.status == JobStatus.DISABLED.value


def test_blacklisting_a_domain_normalises_the_value(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    response = client.post(
        "/api/v1/admin/blacklists",
        headers=admin_headers,
        json={"scope": "domain", "value": "https://www.acme.example/careers"},
    )
    assert response.status_code == 201
    assert response.json()["value"] == "acme.example"

    db.refresh(job)
    assert job.status == JobStatus.DISABLED.value


def test_blacklisting_a_single_job(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    job = make_job(db, company)
    response = client.post(
        "/api/v1/admin/blacklists",
        headers=admin_headers,
        json={"scope": "job", "value": str(job.id)},
    )
    assert response.status_code == 201
    db.refresh(job)
    assert job.status == JobStatus.DISABLED.value


def test_duplicate_blacklist_entries_are_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    payload = {"scope": "domain", "value": "spam.example"}
    assert client.post("/api/v1/admin/blacklists", headers=admin_headers, json=payload).status_code == 201
    assert client.post("/api/v1/admin/blacklists", headers=admin_headers, json=payload).status_code == 409


def test_blacklisted_companies_stay_out_of_recommendations(
    client: TestClient, db: Session, user: User, company: Company, admin_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company)
    db.refresh(user)

    client.post(
        "/api/v1/admin/blacklists",
        headers=admin_headers,
        json={"scope": "company", "value": "Acme Corp"},
    )

    from app.services.recommendations import rank_candidates

    assert rank_candidates(db, user) == []


def test_removing_a_blacklist_entry_clears_the_company_flag(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/admin/blacklists",
        headers=admin_headers,
        json={"scope": "company", "value": "Acme Corp"},
    ).json()

    response = client.delete(f"/api/v1/admin/blacklists/{created['id']}", headers=admin_headers)
    assert response.status_code == 200

    db.refresh(company)
    assert company.is_blacklisted is False
    assert client.get("/api/v1/admin/blacklists", headers=admin_headers).json() == []


def test_sources_can_be_registered_and_disabled(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/admin/sources",
        headers=admin_headers,
        json={
            "name": "Globex Lever",
            "source_type": "lever",
            "external_slug": "globex",
            "company_name": "Globex",
            "company_domain": "globex.example",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    duplicate = client.post(
        "/api/v1/admin/sources",
        headers=admin_headers,
        json={"name": "Globex again", "source_type": "lever", "external_slug": "globex"},
    )
    assert duplicate.status_code == 409

    disabled = client.patch(
        f"/api/v1/admin/sources/{source_id}", headers=admin_headers, json={"is_enabled": False}
    )
    assert disabled.json()["is_enabled"] is False


def test_seeding_default_sources_is_idempotent(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    first = client.post("/api/v1/admin/sources/seed", headers=admin_headers).json()
    assert "Registered" in first["detail"]
    second = client.post("/api/v1/admin/sources/seed", headers=admin_headers).json()
    assert second["detail"] == "Registered 0 new source(s)"


def test_admin_stats_summarise_the_pool(
    client: TestClient, db: Session, company: Company, admin_headers: dict[str, str]
) -> None:
    make_job(db, company)
    make_job(db, company, title="Closed role", status=JobStatus.CLOSED.value)

    stats = client.get("/api/v1/admin/stats", headers=admin_headers).json()
    assert stats["total_jobs"] == 2
    assert stats["active_jobs"] == 1
    assert stats["closed_jobs"] == 1
    assert stats["total_companies"] >= 1
    assert stats["total_users"] >= 1
