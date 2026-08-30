"""Test fixtures: a throwaway Postgres schema, a client, and seeded records."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/jobboard_test",
    ),
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("RESUME_STORAGE_DIR", "./var/test-resumes")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import (  # noqa: E402
    ExperienceLevel,
    JobStatus,
    UserRole,
    WorkArrangement,
)
from app.models.job import Company, Job, JobSource  # noqa: E402
from app.models.resume import Resume  # noqa: E402
from app.models.user import (  # noqa: E402
    EligibilityProfile,
    JobPreferences,
    User,
    UserProfile,
)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate everything between tests so each one starts from empty."""
    yield
    with engine.begin() as connection:
        tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """Client whose requests share the test's session, so both see the same data.

    Each request runs inside its own SAVEPOINT: a request that fails discards
    only its own writes, exactly as a per-request transaction would in
    production, while rows the test set up beforehand survive.
    """

    def _override_get_db() -> Iterator[Session]:
        savepoint = db.begin_nested()
        try:
            yield db
            if savepoint.is_active:
                savepoint.commit()
        except Exception:
            if savepoint.is_active:
                savepoint.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "correct-horse-7",
    role: str = UserRole.USER.value,
    onboarded: bool = True,
) -> User:
    user = User(
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password(password),
        full_name="Test User",
        role=role,
        onboarding_completed_at=datetime.now(timezone.utc) if onboarded else None,
    )
    db.add(user)
    db.flush()
    db.add(
        UserProfile(
            user_id=user.id,
            city="San Francisco",
            region="CA",
            country="US",
            current_title="Software Engineer",
            years_of_experience=6,
        )
    )
    db.add(
        EligibilityProfile(
            user_id=user.id,
            work_authorization="citizen",
            requires_sponsorship=False,
            security_clearance="none",
            authorized_countries=["US"],
            total_years_experience=6,
        )
    )
    db.add(
        JobPreferences(
            user_id=user.id,
            work_arrangements=[WorkArrangement.REMOTE.value, WorkArrangement.HYBRID.value],
            preferred_locations=["San Francisco, CA"],
            desired_titles=["Software Engineer", "Backend Engineer"],
            technologies=["python", "postgresql", "docker"],
            experience_levels=[ExperienceLevel.SENIOR.value, ExperienceLevel.MID.value],
            match_threshold=0,
            max_days_since_posted=90,
        )
    )
    db.flush()
    db.refresh(user)
    return user


@pytest.fixture
def user(db: Session) -> User:
    return make_user(db)


@pytest.fixture
def admin(db: Session) -> User:
    return make_user(db, role=UserRole.ADMIN.value)


def auth_headers(client: TestClient, email: str, password: str = "correct-horse-7") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def user_headers(client: TestClient, user: User) -> dict[str, str]:
    return auth_headers(client, user.email)


@pytest.fixture
def admin_headers(client: TestClient, admin: User) -> dict[str, str]:
    return auth_headers(client, admin.email)


@pytest.fixture
def company(db: Session) -> Company:
    record = Company(name="Acme Corp", slug="acme-corp", domain="acme.example")
    db.add(record)
    db.flush()
    return record


@pytest.fixture
def source(db: Session, company: Company) -> JobSource:
    record = JobSource(
        company_id=company.id,
        name="Acme Greenhouse",
        source_type="greenhouse",
        external_slug="acme",
    )
    db.add(record)
    db.flush()
    return record


def make_job(
    db: Session,
    company: Company,
    *,
    title: str = "Senior Backend Engineer",
    description: str | None = None,
    location: str | None = "San Francisco, CA",
    work_arrangement: str = WorkArrangement.REMOTE.value,
    status: str = JobStatus.ACTIVE.value,
    required_skills: list[str] | None = None,
    technologies: list[str] | None = None,
    salary_min: int | None = 150_000,
    salary_max: int | None = 200_000,
    min_years_experience: float | None = 5,
    experience_level: str = ExperienceLevel.SENIOR.value,
    date_posted: date | None = None,
    external_id: str | None = None,
    source: JobSource | None = None,
    **extra: object,
) -> Job:
    from app.services.dedupe import compute_fingerprint

    now = datetime.now(timezone.utc)
    job = Job(
        company_id=company.id,
        source_id=source.id if source else None,
        external_id=external_id or uuid.uuid4().hex[:10],
        title=title,
        description=description or "Build Python services with PostgreSQL and Docker.",
        description_snapshot=description or "Build Python services with PostgreSQL and Docker.",
        location=location,
        city="San Francisco",
        region="CA",
        country="US",
        work_arrangement=work_arrangement,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency="USD",
        salary_period="year",
        experience_level=experience_level,
        min_years_experience=min_years_experience,
        technologies=technologies if technologies is not None else ["python", "postgresql"],
        required_skills=required_skills if required_skills is not None else ["python", "postgresql"],
        preferred_skills=["docker"],
        status=status,
        source_url=f"https://boards.example/{uuid.uuid4().hex[:8]}",
        fingerprint=compute_fingerprint(company.slug, title, location),
        first_seen_at=now,
        last_verified_at=now,
        last_checked_at=now,
        date_posted=date_posted or (now - timedelta(days=3)).date(),
        **extra,
    )
    db.add(job)
    db.flush()
    return job


@pytest.fixture
def job(db: Session, company: Company) -> Job:
    return make_job(db, company)


def make_resume(db: Session, user: User, **content: object) -> Resume:
    parsed = {
        "full_name": "Test User",
        "skills": ["python", "postgresql", "docker", "fastapi"],
        "job_titles": ["Senior Backend Engineer", "Software Engineer"],
        "experience": [],
        "education": [],
        "certifications": [],
        "years_of_experience": 6,
    }
    parsed.update(content)
    resume = Resume(
        user_id=user.id,
        label="Primary resume",
        original_filename="resume.pdf",
        content_type="application/pdf",
        file_size=1024,
        version=1,
        is_default=True,
        parse_status="parsed",
        parsed_data=parsed,
        parsed_at=datetime.now(timezone.utc),
    )
    db.add(resume)
    db.flush()
    return resume


@pytest.fixture
def resume(db: Session, user: User) -> Resume:
    return make_resume(db, user)
