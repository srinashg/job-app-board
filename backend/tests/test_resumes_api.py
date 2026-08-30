"""Features 2 and 3: resume upload, editing and version management."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

RESUME_TEXT = b"""Ada Lovelace
ada@example.com

SKILLS
Python, PostgreSQL, Docker

EXPERIENCE
Backend Engineer | Analytical Engines
2019 - Present
- Wrote Python services
"""


def upload(client: TestClient, headers: dict[str, str], *, label: str | None = None, name: str = "resume.txt"):
    data = {"label": label} if label else {}
    return client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": (name, RESUME_TEXT, "text/plain")},
        data=data,
    )


def test_upload_parses_and_becomes_the_default(client: TestClient, user_headers: dict[str, str]) -> None:
    response = upload(client, user_headers, label="Main resume")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["label"] == "Main resume"
    assert body["parse_status"] == "parsed"
    assert body["is_default"] is True
    assert "python" in body["content"]["skills"]
    assert body["content"]["job_titles"]


def test_second_upload_does_not_steal_the_default(client: TestClient, user_headers: dict[str, str]) -> None:
    first = upload(client, user_headers, label="First").json()
    second = upload(client, user_headers, label="Second").json()
    assert first["is_default"] is True
    assert second["is_default"] is False
    assert second["version"] == 2


def test_switching_the_default_clears_the_previous_one(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    first = upload(client, user_headers, label="First").json()
    second = upload(client, user_headers, label="Second").json()

    promoted = client.post(f"/api/v1/resumes/{second['id']}/default", headers=user_headers)
    assert promoted.status_code == 200
    assert promoted.json()["is_default"] is True

    listing = client.get("/api/v1/resumes", headers=user_headers).json()
    defaults = [item for item in listing if item["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == second["id"]
    assert next(item for item in listing if item["id"] == first["id"])["is_default"] is False


def test_rename_a_version(client: TestClient, user_headers: dict[str, str]) -> None:
    resume = upload(client, user_headers).json()
    response = client.patch(
        f"/api/v1/resumes/{resume['id']}", headers=user_headers, json={"label": "Renamed"}
    )
    assert response.status_code == 200
    assert response.json()["label"] == "Renamed"


def test_edits_override_parsed_fields_and_survive_a_reparse(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    resume = upload(client, user_headers).json()
    edited = client.put(
        f"/api/v1/resumes/{resume['id']}/content",
        headers=user_headers,
        json={
            "skills": ["Python", "Kubernetes", "Terraform"],
            "job_titles": ["Staff Engineer"],
            "years_of_experience": 9,
        },
    )
    assert edited.status_code == 200
    content = edited.json()["content"]
    assert content["skills"] == ["python", "kubernetes", "terraform"]
    assert content["job_titles"] == ["Staff Engineer"]
    assert content["years_of_experience"] == 9

    reparsed = client.post(f"/api/v1/resumes/{resume['id']}/reparse", headers=user_headers)
    assert reparsed.status_code == 200
    # Re-parsing refreshes the extraction but must not discard user corrections.
    assert reparsed.json()["content"]["job_titles"] == ["Staff Engineer"]


def test_delete_removes_the_file_and_promotes_another_version(
    client: TestClient, user_headers: dict[str, str], db: Session
) -> None:
    first = upload(client, user_headers, label="First").json()
    second = upload(client, user_headers, label="Second").json()

    response = client.delete(f"/api/v1/resumes/{first['id']}", headers=user_headers)
    assert response.status_code == 200

    listing = client.get("/api/v1/resumes", headers=user_headers).json()
    assert [item["id"] for item in listing] == [second["id"]]
    assert listing[0]["is_default"] is True

    assert client.get(f"/api/v1/resumes/{first['id']}", headers=user_headers).status_code == 404


def test_download_returns_the_stored_file(client: TestClient, user_headers: dict[str, str]) -> None:
    resume = upload(client, user_headers).json()
    response = client.get(f"/api/v1/resumes/{resume['id']}/file", headers=user_headers)
    assert response.status_code == 200
    assert b"Ada Lovelace" in response.content


def test_empty_upload_is_rejected(client: TestClient, user_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/resumes",
        headers=user_headers,
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400


def test_unparseable_upload_is_kept_and_flagged(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/resumes",
        headers=user_headers,
        files={"file": ("resume.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["parse_status"] == "failed"
    assert body["parse_error"]


def test_a_user_cannot_read_another_users_resume(
    client: TestClient, db: Session, user_headers: dict[str, str]
) -> None:
    from tests.conftest import auth_headers, make_user

    resume = upload(client, user_headers).json()
    other = make_user(db, email="other@example.com")
    other_headers = auth_headers(client, other.email)

    assert client.get(f"/api/v1/resumes/{resume['id']}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/resumes/{resume['id']}", headers=other_headers).status_code == 404
