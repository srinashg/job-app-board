"""Feature 15: privacy controls, data export and account deletion."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.resume import Resume
from app.models.user import User
from app.services import resume_storage

RESUME_BYTES = b"Ada Lovelace\n\nSKILLS\nPython, PostgreSQL\n"


def upload(client: TestClient, headers: dict[str, str]):
    return client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("resume.txt", RESUME_BYTES, "text/plain")},
    )


def test_the_summary_reports_what_is_stored(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    upload(client, user_headers)
    client.post(
        "/api/v1/applications",
        headers=user_headers,
        json={"company_name": "Initech", "position_title": "Engineer"},
    )

    summary = client.get("/api/v1/privacy/summary", headers=user_headers).json()
    assert summary["resume_count"] == 1
    assert summary["stored_resume_files"] == 1
    assert summary["application_count"] == 1
    assert any(item["consent_type"] for item in summary["consents"]) or summary["consents"] == []


def test_export_returns_the_users_own_data(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    upload(client, user_headers)
    client.put(
        "/api/v1/me/profile", headers=user_headers, json={"phone": "+1 415 555 0134"}
    )
    client.post(
        "/api/v1/applications",
        headers=user_headers,
        json={"company_name": "Initech", "position_title": "Engineer"},
    )
    client.post(
        "/api/v1/contacts", headers=user_headers, json={"name": "Dana", "email": "dana@x.example"}
    )

    export = client.get("/api/v1/privacy/export", headers=user_headers).json()
    assert export["user"]["email"]
    # Encrypted columns are decrypted for the owner's own export.
    assert export["profile"]["phone"] == "+1 415 555 0134"
    assert len(export["resumes"]) == 1
    assert len(export["applications"]) == 1
    assert export["contacts"][0]["email"] == "dana@x.example"


def test_deleting_all_resumes_removes_the_files_and_content(
    client: TestClient, db: Session, user: User, user_headers: dict[str, str]
) -> None:
    resume_id = upload(client, user_headers).json()["id"]
    stored = db.get(Resume, resume_id)
    db.refresh(stored)
    assert resume_storage.read(stored.storage_path) is not None

    response = client.delete("/api/v1/privacy/resumes", headers=user_headers)
    assert response.status_code == 200

    db.refresh(stored)
    assert stored.storage_path is None
    assert stored.raw_text is None
    assert stored.parsed_data == {}
    assert stored.deleted_at is not None
    assert client.get("/api/v1/resumes", headers=user_headers).json() == []


def test_account_deletion_requires_the_confirmation_word(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.request(
        "DELETE",
        "/api/v1/privacy/account",
        headers=user_headers,
        json={"confirmation": "yes", "password": "correct-horse-7"},
    )
    assert response.status_code == 400
    assert "DELETE" in response.json()["detail"]


def test_account_deletion_requires_the_password(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.request(
        "DELETE",
        "/api/v1/privacy/account",
        headers=user_headers,
        json={"confirmation": "DELETE", "password": "wrong-password-1"},
    )
    assert response.status_code == 401


def test_account_deletion_removes_every_trace(
    client: TestClient, db: Session, user: User, user_headers: dict[str, str]
) -> None:
    user_id = user.id
    upload(client, user_headers)
    client.post(
        "/api/v1/applications",
        headers=user_headers,
        json={"company_name": "Initech", "position_title": "Engineer"},
    )
    client.post("/api/v1/contacts", headers=user_headers, json={"name": "Dana"})

    response = client.request(
        "DELETE",
        "/api/v1/privacy/account",
        headers=user_headers,
        json={"confirmation": "DELETE", "password": "correct-horse-7"},
    )
    assert response.status_code == 200

    assert db.get(User, user_id) is None
    assert db.execute(select(Resume).where(Resume.user_id == user_id)).first() is None
    assert db.execute(select(Application).where(Application.user_id == user_id)).first() is None
    # The token no longer resolves to an account.
    assert client.get("/api/v1/me", headers=user_headers).status_code == 401


def test_consent_can_be_granted_and_withdrawn(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    granted = client.post(
        "/api/v1/me/consents",
        headers=user_headers,
        json={"consent_type": "marketing_email", "granted": True, "document_version": "v1"},
    )
    assert granted.status_code == 201

    withdrawn = client.post(
        "/api/v1/me/consents",
        headers=user_headers,
        json={"consent_type": "marketing_email", "granted": False},
    )
    assert withdrawn.status_code == 201

    history = client.get("/api/v1/me/consents", headers=user_headers).json()
    marketing = [item for item in history if item["consent_type"] == "marketing_email"]
    # The audit trail keeps both events rather than overwriting the first.
    assert len(marketing) == 2
    assert marketing[0]["granted"] is False


def test_privacy_endpoints_need_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/privacy/summary").status_code == 401
    assert client.get("/api/v1/privacy/export").status_code == 401
    assert client.delete("/api/v1/privacy/resumes").status_code == 401


def test_resume_storage_refuses_paths_outside_the_root() -> None:
    assert resume_storage.read("../../etc/passwd") is None
    assert resume_storage.delete("../../etc/passwd") is False
