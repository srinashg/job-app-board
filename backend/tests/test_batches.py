"""Features 7 and 8: the five-job batch loop and the skip system."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import BatchStatus, JobStatus, RecommendationStatus
from app.models.job import Company
from app.models.recommendation import Batch, Recommendation
from app.models.user import User
from tests.conftest import make_job, make_resume

TITLES = [
    "Senior Backend Engineer",
    "Backend Engineer",
    "Platform Engineer",
    "Infrastructure Engineer",
    "Python Engineer",
    "Distributed Systems Engineer",
    "Data Platform Engineer",
    "API Engineer",
]


def seed_jobs(db: Session, company: Company, count: int) -> list:
    return [make_job(db, company, title=TITLES[index % len(TITLES)] + f" {index}") for index in range(count)]


def prepare(db: Session, user: User, company: Company, job_count: int = 8) -> None:
    make_resume(db, user)
    seed_jobs(db, company, job_count)
    db.refresh(user)


def test_current_batch_holds_exactly_five_jobs(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company)
    response = client.get("/api/v1/batches/current", headers=user_headers)
    assert response.status_code == 200

    body = response.json()
    assert body["batch"] is not None
    assert len(body["batch"]["recommendations"]) == 5
    assert body["remaining"] == 5
    assert body["batch"]["sequence"] == 1


def test_recommendations_are_ordered_by_match_score(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    scores = [item["match_score"] for item in batch["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    assert all(item["match_explanation"] is not None for item in batch["recommendations"])


def test_the_next_batch_is_locked_until_all_five_are_resolved(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=12)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]

    blocked = client.post("/api/v1/batches/next", headers=user_headers)
    assert blocked.status_code == 409
    assert "remaining" in blocked.json()["detail"]

    for recommendation in batch["recommendations"][:4]:
        skip = client.post(
            f"/api/v1/batches/recommendations/{recommendation['id']}/skip",
            headers=user_headers,
            json={"reason": "not_interested"},
        )
        assert skip.status_code == 200

    still_blocked = client.post("/api/v1/batches/next", headers=user_headers)
    assert still_blocked.status_code == 409

    last = batch["recommendations"][4]
    client.post(
        f"/api/v1/batches/recommendations/{last['id']}/skip",
        headers=user_headers,
        json={"reason": "not_interested"},
    )

    unlocked = client.post("/api/v1/batches/next", headers=user_headers)
    assert unlocked.status_code == 200
    assert unlocked.json()["batch"]["sequence"] == 2
    assert len(unlocked.json()["batch"]["recommendations"]) == 5


def test_a_job_is_never_recommended_twice(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=12)
    first = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    first_ids = {item["job_id"] for item in first["recommendations"]}

    for recommendation in first["recommendations"]:
        client.post(
            f"/api/v1/batches/recommendations/{recommendation['id']}/skip",
            headers=user_headers,
            json={"reason": "not_interested"},
        )

    second = client.post("/api/v1/batches/next", headers=user_headers).json()["batch"]
    second_ids = {item["job_id"] for item in second["recommendations"]}
    assert first_ids.isdisjoint(second_ids)


def test_skipping_records_the_reason(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    target = batch["recommendations"][0]

    response = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/skip",
        headers=user_headers,
        json={"reason": "salary", "note": "Below my range"},
    )
    assert response.status_code == 200
    assert response.json()["remaining"] == 4

    stored = db.get(Recommendation, target["id"])
    db.refresh(stored)
    assert stored.status == RecommendationStatus.SKIPPED.value
    assert stored.skip_reason == "salary"
    assert stored.skip_note == "Below my range"


def test_every_documented_skip_reason_is_accepted(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    reasons = [
        "not_qualified",
        "already_applied",
        "closed",
        "location",
        "salary",
        "sponsorship",
        "clearance",
        "experience_level",
        "not_interested",
    ]
    prepare(db, user, company, job_count=40)
    for reason in reasons:
        state = client.get("/api/v1/batches/current", headers=user_headers).json()
        if state["batch"] is None:
            client.post("/api/v1/batches/next", headers=user_headers)
            state = client.get("/api/v1/batches/current", headers=user_headers).json()
        target = next(
            item for item in state["batch"]["recommendations"] if item["status"] == "active"
        )
        response = client.post(
            f"/api/v1/batches/recommendations/{target['id']}/skip",
            headers=user_headers,
            json={"reason": reason},
        )
        assert response.status_code == 200, f"{reason}: {response.text}"


def test_skipping_as_already_applied_pulls_in_a_replacement(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=12)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    target = batch["recommendations"][0]

    response = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/skip",
        headers=user_headers,
        json={"reason": "already_applied"},
    )
    body = response.json()

    # The batch still asks for five real decisions.
    assert len(body["batch"]["recommendations"]) == 5
    assert body["remaining"] == 5
    assert target["id"] not in {item["id"] for item in body["batch"]["recommendations"]}


def test_skipping_for_a_personal_reason_does_not_replace(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=12)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    target = batch["recommendations"][0]

    body = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/skip",
        headers=user_headers,
        json={"reason": "not_interested"},
    ).json()
    assert body["remaining"] == 4
    assert len(body["batch"]["recommendations"]) == 5


def test_a_job_that_closes_is_replaced_when_the_batch_is_read(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=12)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    doomed = batch["recommendations"][0]

    from app.models.job import Job

    job = db.get(Job, doomed["job_id"])
    job.status = JobStatus.CLOSED.value
    db.flush()

    refreshed = client.get("/api/v1/batches/current", headers=user_headers).json()
    ids = {item["id"] for item in refreshed["batch"]["recommendations"]}
    assert doomed["id"] not in ids
    assert refreshed["remaining"] == 5


def test_a_resolved_recommendation_cannot_be_skipped_again(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    target = batch["recommendations"][0]

    client.post(
        f"/api/v1/batches/recommendations/{target['id']}/skip",
        headers=user_headers,
        json={"reason": "location"},
    )
    again = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/skip",
        headers=user_headers,
        json={"reason": "salary"},
    )
    assert again.status_code == 409


def test_saving_a_job_does_not_resolve_it(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    target = batch["recommendations"][0]

    saved = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/save", headers=user_headers
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "saved"

    state = client.get("/api/v1/batches/current", headers=user_headers).json()
    assert state["remaining"] == 5

    listing = client.get("/api/v1/batches/saved", headers=user_headers).json()
    assert [item["id"] for item in listing] == [target["id"]]

    unsaved = client.post(
        f"/api/v1/batches/recommendations/{target['id']}/unsave", headers=user_headers
    )
    assert unsaved.json()["status"] == "active"


def test_an_exhausted_pool_reports_itself(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    db.refresh(user)
    response = client.get("/api/v1/batches/current", headers=user_headers).json()

    assert response["batch"] is None
    assert response["exhausted"] is True
    assert "No jobs match" in response["message"]


def test_a_short_pool_produces_a_smaller_batch(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=3)
    batch = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    assert len(batch["recommendations"]) == 3


def test_the_match_threshold_filters_the_pool(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    """Weak matches drop out of the pool once the threshold is raised past them."""
    make_resume(db, user)
    weak = make_job(
        db,
        company,
        title="Salesforce Administrator",
        required_skills=["salesforce", "sap"],
        technologies=["salesforce"],
        description="Administer Salesforce and SAP.",
    )
    db.refresh(user)

    included = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    assert [item["job_id"] for item in included["recommendations"]] == [str(weak.id)]
    assert included["recommendations"][0]["match_score"] < 60

    user.preferences.match_threshold = 60
    db.flush()

    state = client.delete("/api/v1/batches/current", headers=user_headers).json()
    assert state["batch"] is None
    assert state["exhausted"] is True


def test_discarding_a_batch_releases_unresolved_jobs(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    prepare(db, user, company, job_count=6)
    first = client.get("/api/v1/batches/current", headers=user_headers).json()["batch"]
    first_ids = {item["job_id"] for item in first["recommendations"]}

    discarded = client.delete("/api/v1/batches/current", headers=user_headers)
    assert discarded.status_code == 200

    second = discarded.json()["batch"]
    assert second["sequence"] == 2
    # The released jobs are eligible again.
    assert first_ids & {item["job_id"] for item in second["recommendations"]}


def test_the_batch_endpoints_require_onboarding(client: TestClient, db: Session) -> None:
    from tests.conftest import auth_headers, make_user

    account = make_user(db, email="pending@example.com", onboarded=False)
    headers = auth_headers(client, account.email)
    assert client.get("/api/v1/batches/current", headers=headers).status_code == 409


def test_preview_scores_without_consuming_the_pool(
    client: TestClient, db: Session, user: User, company: Company, user_headers: dict[str, str]
) -> None:
    make_resume(db, user)
    seed_jobs(db, company, 6)
    db.refresh(user)

    preview = client.get("/api/v1/batches/preview", headers=user_headers).json()
    assert len(preview) == 6
    assert db.execute(select(Batch)).scalars().first() is None
    assert db.execute(select(Recommendation)).scalars().first() is None
