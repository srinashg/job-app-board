"""Features 11, 12 and 13: tracker, history and dashboard."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import ApplicationStatus
from app.models.job import Company
from app.models.user import User
from tests.conftest import make_job, make_resume

MANUAL = {
    "company_name": "Initech",
    "position_title": "TPS Report Engineer",
    "location": "Austin, TX",
    "work_arrangement": "hybrid",
    "work_address": "1 Initech Plaza, Austin, TX",
    "application_url": "https://initech.example/jobs/1",
    "status": "applied",
    "notes": "Referred by a friend",
}


def test_applying_from_a_batch_snapshots_the_job(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    resume = make_resume(db, user)
    job = make_job(db, company)
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    recommendation = batch["recommendations"][0]

    response = client.post(
        f"/api/v1/batches/recommendations/{recommendation['id']}/apply",
        headers=user_headers,
        json={"resume_id": str(resume.id), "notes": "Applied via careers page"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["company_name"] == company.name
    assert body["position_title"] == job.title
    assert body["status"] == "applied"
    assert body["applied_at"] == date.today().isoformat()
    assert body["resume_id"] == str(resume.id)
    assert body["match_score"] == recommendation["match_score"]

    detail = client.get(f"/api/v1/applications/{body['id']}", headers=user_headers).json()
    assert detail["job_description_snapshot"] == job.description_snapshot
    assert detail["events"][0]["to_status"] == "applied"

    state = client.get("/api/v1/batches/current", headers=user_headers).json()
    assert state["remaining"] == 0 or state["batch"] is None


def test_a_remote_role_records_no_street_address(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, work_arrangement="remote", street_address="500 Market St")
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    application = client.post(
        f"/api/v1/batches/recommendations/{batch['recommendations'][0]['id']}/apply",
        headers=user_headers,
        json={},
    ).json()

    assert application["work_arrangement"] == "remote"
    assert application["work_address"] is None


def test_a_hybrid_role_records_the_address(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    make_job(db, company, work_arrangement="hybrid", street_address="500 Market St")
    db.refresh(user)

    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    application = client.post(
        f"/api/v1/batches/recommendations/{batch['recommendations'][0]['id']}/apply",
        headers=user_headers,
        json={},
    ).json()

    assert application["work_arrangement"] == "hybrid"
    assert "500 Market St" in application["work_address"]


def test_a_manual_application_is_accepted(client: TestClient, user_headers: dict[str, str]) -> None:
    response = client.post("/api/v1/applications", json=MANUAL, headers=user_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["company_name"] == "Initech"
    assert body["work_address"] == MANUAL["work_address"]
    assert body["notes"] == "Referred by a friend"


def test_a_manual_application_needs_company_and_title(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/applications", json={"company_name": "Initech"}, headers=user_headers
    )
    assert response.status_code == 400


def test_the_full_status_pipeline(client: TestClient, user_headers: dict[str, str]) -> None:
    application = client.post("/api/v1/applications", json=MANUAL, headers=user_headers).json()

    for target in ["interview", "offer"]:
        response = client.post(
            f"/api/v1/applications/{application['id']}/status",
            headers=user_headers,
            json={"status": target},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target

    detail = client.get(f"/api/v1/applications/{application['id']}", headers=user_headers).json()
    assert [event["to_status"] for event in detail["events"]] == ["applied", "interview", "offer"]
    assert detail["first_response_at"] is not None


def test_an_illegal_transition_is_refused(client: TestClient, user_headers: dict[str, str]) -> None:
    application = client.post("/api/v1/applications", json=MANUAL, headers=user_headers).json()
    client.post(
        f"/api/v1/applications/{application['id']}/status",
        headers=user_headers,
        json={"status": "rejected"},
    )
    response = client.post(
        f"/api/v1/applications/{application['id']}/status",
        headers=user_headers,
        json={"status": "offer"},
    )
    assert response.status_code == 409


def test_every_tracker_status_is_reachable(client: TestClient, user_headers: dict[str, str]) -> None:
    """Todo, Applied, Interview, Offer, Rejected, Withdrawn, Skipped and Closed."""
    reachable = set()
    for target, start in [
        ("applied", "todo"),
        ("interview", "applied"),
        ("offer", "applied"),
        ("rejected", "applied"),
        ("withdrawn", "applied"),
        ("skipped", "todo"),
        ("closed", "todo"),
    ]:
        application = client.post(
            "/api/v1/applications", json={**MANUAL, "status": start}, headers=user_headers
        ).json()
        reachable.add(application["status"])
        response = client.post(
            f"/api/v1/applications/{application['id']}/status",
            headers=user_headers,
            json={"status": target},
        )
        assert response.status_code == 200, f"{start} -> {target}: {response.text}"
        reachable.add(response.json()["status"])

    assert reachable == {status.value for status in ApplicationStatus}


def test_filtering_and_searching_the_history(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    client.post("/api/v1/applications", json=MANUAL, headers=user_headers)
    client.post(
        "/api/v1/applications",
        json={**MANUAL, "company_name": "Globex", "position_title": "Data Engineer"},
        headers=user_headers,
    )

    all_rows = client.get("/api/v1/applications", headers=user_headers).json()
    assert all_rows["total"] == 2

    filtered = client.get("/api/v1/applications?status=applied", headers=user_headers).json()
    assert filtered["total"] == 2

    searched = client.get("/api/v1/applications?q=globex", headers=user_headers).json()
    assert searched["total"] == 1
    assert searched["items"][0]["company_name"] == "Globex"


def test_recruiter_contacts_are_linked_and_encrypted(
    client: TestClient, db: Session, user_headers: dict[str, str]
) -> None:
    contact = client.post(
        "/api/v1/contacts",
        headers=user_headers,
        json={
            "name": "Dana Recruiter",
            "email": "dana@initech.example",
            "phone": "+1 512 555 0100",
            "company_name": "Initech",
        },
    )
    assert contact.status_code == 201
    contact_id = contact.json()["id"]
    assert contact.json()["email"] == "dana@initech.example"

    from sqlalchemy import text

    stored = db.execute(text("SELECT email, phone FROM contacts")).first()
    assert "dana@initech.example" not in (stored[0] or "")
    assert "555 0100" not in (stored[1] or "")

    application = client.post(
        "/api/v1/applications",
        json={**MANUAL, "contact_id": contact_id},
        headers=user_headers,
    ).json()
    detail = client.get(f"/api/v1/applications/{application['id']}", headers=user_headers).json()
    assert detail["contact"]["name"] == "Dana Recruiter"


def test_the_dashboard_reports_counts_and_rates(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    ids = []
    for index in range(4):
        response = client.post(
            "/api/v1/applications",
            json={**MANUAL, "company_name": f"Company {index}"},
            headers=user_headers,
        )
        ids.append(response.json()["id"])

    client.post(
        f"/api/v1/applications/{ids[0]}/status", headers=user_headers, json={"status": "interview"}
    )
    client.post(
        f"/api/v1/applications/{ids[1]}/status", headers=user_headers, json={"status": "rejected"}
    )

    stats = client.get("/api/v1/dashboard", headers=user_headers).json()
    assert stats["total_applications"] == 4
    assert stats["interviews"] == 1
    assert stats["rejections"] == 1
    assert stats["responses"] == 2
    assert stats["response_rate"] == 50.0
    assert stats["interview_rate"] == 25.0
    assert stats["offer_rate"] == 0.0
    assert stats["in_pipeline"] == 3
    assert stats["applications_last_7_days"] == 4
    assert {row["status"] for row in stats["pipeline_by_status"]} == {
        item.value for item in ApplicationStatus
    }


def test_the_dashboard_is_empty_for_a_new_account(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    stats = client.get("/api/v1/dashboard", headers=user_headers).json()
    assert stats["total_applications"] == 0
    assert stats["response_rate"] == 0.0


def test_applications_are_scoped_to_their_owner(
    client: TestClient, db: Session, user_headers: dict[str, str]
) -> None:
    from tests.conftest import auth_headers, make_user

    mine = client.post("/api/v1/applications", json=MANUAL, headers=user_headers).json()
    other = make_user(db, email="stranger@example.com")
    other_headers = auth_headers(client, other.email)

    assert client.get(f"/api/v1/applications/{mine['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/v1/applications", headers=other_headers).json()["total"] == 0
