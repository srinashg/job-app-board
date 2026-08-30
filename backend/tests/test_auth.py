"""Feature 1: authentication, onboarding, profile, eligibility, preferences."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import make_user

REGISTRATION = {
    "email": "new.user@example.com",
    "password": "correct-horse-7",
    "full_name": "New User",
    "accepted_terms": True,
}


def test_register_returns_tokens_and_bootstraps_records(client: TestClient, db: Session) -> None:
    response = client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"] and body["refresh_token"]

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/me/profile", headers=headers).status_code == 200
    assert client.get("/api/v1/me/eligibility", headers=headers).status_code == 200
    assert client.get("/api/v1/me/preferences", headers=headers).status_code == 200

    consents = client.get("/api/v1/me/consents", headers=headers).json()
    assert {record["consent_type"] for record in consents} == {
        "terms_of_service",
        "privacy_policy",
    }


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    assert client.post("/api/v1/auth/register", json=REGISTRATION).status_code == 201
    assert client.post("/api/v1/auth/register", json=REGISTRATION).status_code == 409


def test_register_requires_terms_and_strong_password(client: TestClient) -> None:
    without_terms = {**REGISTRATION, "accepted_terms": False}
    assert client.post("/api/v1/auth/register", json=without_terms).status_code == 422

    weak = {**REGISTRATION, "password": "short1"}
    assert client.post("/api/v1/auth/register", json=weak).status_code == 422

    no_digits = {**REGISTRATION, "password": "allletterspassword"}
    assert client.post("/api/v1/auth/register", json=no_digits).status_code == 422


def test_login_and_refresh(client: TestClient, db: Session) -> None:
    account = make_user(db, email="login@example.com")
    response = client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": "correct-horse-7"}
    )
    assert response.status_code == 200
    refresh_token = response.json()["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_login_rejects_bad_password(client: TestClient, db: Session) -> None:
    account = make_user(db, email="wrongpass@example.com")
    response = client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": "not-the-password-1"}
    )
    assert response.status_code == 401


def test_access_token_cannot_be_used_as_refresh_token(client: TestClient, db: Session) -> None:
    account = make_user(db, email="mixed@example.com")
    tokens = client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": "correct-horse-7"}
    ).json()
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401


def test_protected_route_requires_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_oauth_authorize_reports_missing_configuration(client: TestClient) -> None:
    response = client.get("/api/v1/auth/oauth/google/authorize")
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


def test_oauth_rejects_unknown_provider(client: TestClient) -> None:
    response = client.get("/api/v1/auth/oauth/myspace/authorize")
    assert response.status_code == 400


def test_password_change_requires_the_current_password(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "nope-12345", "new_password": "brand-new-pass-9"},
        headers=user_headers,
    )
    assert wrong.status_code == 401

    correct = client.post(
        "/api/v1/auth/password",
        json={"current_password": "correct-horse-7", "new_password": "brand-new-pass-9"},
        headers=user_headers,
    )
    assert correct.status_code == 200


def test_onboarding_saves_every_section_and_completes(client: TestClient, db: Session) -> None:
    tokens = client.post("/api/v1/auth/register", json=REGISTRATION).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    status_before = client.get("/api/v1/me/onboarding", headers=headers).json()
    assert status_before["completed"] is False
    assert status_before["next_step"] == "profile"

    response = client.post(
        "/api/v1/me/onboarding",
        headers=headers,
        json={
            "profile": {"city": "Austin", "region": "TX", "current_title": "Data Engineer"},
            "eligibility": {
                "work_authorization": "needs_sponsorship",
                "requires_sponsorship": True,
                "minimum_salary": 120000,
            },
            "preferences": {
                "work_arrangements": ["remote"],
                "desired_titles": ["Data Engineer"],
                "technologies": ["python", "spark"],
                "match_threshold": 60,
            },
            "consents": [{"consent_type": "resume_processing", "granted": True}],
        },
    )
    assert response.status_code == 200
    assert response.json()["completed"] is True

    eligibility = client.get("/api/v1/me/eligibility", headers=headers).json()
    assert eligibility["requires_sponsorship"] is True
    assert eligibility["minimum_salary"] == 120000

    preferences = client.get("/api/v1/me/preferences", headers=headers).json()
    assert preferences["technologies"] == ["python", "spark"]
    assert preferences["match_threshold"] == 60

    consents = client.get("/api/v1/me/consents", headers=headers).json()
    assert any(record["consent_type"] == "resume_processing" for record in consents)


def test_profile_personal_fields_are_encrypted_at_rest(
    client: TestClient, db: Session, user_headers: dict[str, str]
) -> None:
    response = client.put(
        "/api/v1/me/profile",
        headers=user_headers,
        json={"phone": "+1 415 555 0134", "street_address": "500 Market St"},
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+1 415 555 0134"

    from sqlalchemy import text

    stored = db.execute(text("SELECT phone, street_address FROM user_profiles")).first()
    assert stored is not None
    assert "555 0134" not in (stored[0] or "")
    assert "Market" not in (stored[1] or "")
