"""Seed a development database with sources, jobs and a demo account.

Usage: python -m scripts.seed [--with-demo-user]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import ExperienceLevel, UserRole, WorkArrangement
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import EligibilityProfile, JobPreferences, User, UserProfile
from app.services.dedupe import compute_fingerprint
from app.services.ingestion import get_or_create_company, seed_default_sources

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-1"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password-1"

SAMPLE_JOBS = [
    {
        "company": "Northwind Systems",
        "domain": "northwind.example",
        "title": "Senior Backend Engineer",
        "location": "San Francisco, CA",
        "work_arrangement": WorkArrangement.REMOTE.value,
        "salary": (170_000, 210_000),
        "level": ExperienceLevel.SENIOR.value,
        "years": 6,
        "required": ["python", "postgresql", "docker"],
        "preferred": ["kubernetes", "fastapi"],
        "description": (
            "Northwind is hiring a senior backend engineer to own our billing "
            "platform.\n\nRequirements\n- 6+ years of experience\n- Python and "
            "PostgreSQL in production\n- Docker\n\nNice to have\n- Kubernetes\n- FastAPI"
        ),
    },
    {
        "company": "Contoso Analytics",
        "domain": "contoso.example",
        "title": "Data Platform Engineer",
        "location": "Austin, TX",
        "work_arrangement": WorkArrangement.HYBRID.value,
        "street": "600 Congress Ave, Austin, TX",
        "salary": (150_000, 185_000),
        "level": ExperienceLevel.MID.value,
        "years": 4,
        "required": ["python", "spark", "airflow"],
        "preferred": ["dbt", "snowflake"],
        "description": (
            "Build the pipelines behind our analytics products.\n\nRequirements\n"
            "- 4+ years of experience\n- Python, Spark and Airflow\n\nNice to have\n- dbt\n- Snowflake"
        ),
    },
    {
        "company": "Fabrikam Cloud",
        "domain": "fabrikam.example",
        "title": "Platform Engineer",
        "location": "Remote - US",
        "work_arrangement": WorkArrangement.REMOTE.value,
        "salary": (160_000, 195_000),
        "level": ExperienceLevel.SENIOR.value,
        "years": 5,
        "required": ["kubernetes", "terraform", "aws"],
        "preferred": ["go", "python"],
        "description": (
            "Run the platform our product teams deploy on.\n\nRequirements\n"
            "- 5+ years of experience\n- Kubernetes, Terraform and AWS\n\nNice to have\n- Go\n- Python"
        ),
    },
    {
        "company": "Tailspin Security",
        "domain": "tailspin.example",
        "title": "Security Engineer",
        "location": "Washington, DC",
        "work_arrangement": WorkArrangement.ONSITE.value,
        "street": "1200 K St NW, Washington, DC",
        "salary": (155_000, 190_000),
        "level": ExperienceLevel.SENIOR.value,
        "years": 5,
        "required": ["python", "linux"],
        "preferred": ["aws"],
        "clearance": "secret",
        "description": (
            "Secure federal workloads. An active Secret clearance is required.\n\n"
            "Requirements\n- 5+ years of experience\n- Python and Linux"
        ),
    },
    {
        "company": "Adventure Works",
        "domain": "adventureworks.example",
        "title": "Full Stack Engineer",
        "location": "New York, NY",
        "work_arrangement": WorkArrangement.HYBRID.value,
        "street": "40 W 25th St, New York, NY",
        "salary": (140_000, 175_000),
        "level": ExperienceLevel.MID.value,
        "years": 3,
        "required": ["typescript", "react", "node.js"],
        "preferred": ["next.js", "postgresql"],
        "description": (
            "Ship product features end to end.\n\nRequirements\n- 3+ years of "
            "experience\n- TypeScript, React and Node.js\n\nNice to have\n- Next.js\n- PostgreSQL"
        ),
    },
    {
        "company": "Northwind Systems",
        "domain": "northwind.example",
        "title": "Staff Software Engineer",
        "location": "Remote - US",
        "work_arrangement": WorkArrangement.REMOTE.value,
        "salary": (200_000, 250_000),
        "level": ExperienceLevel.LEAD.value,
        "years": 8,
        "required": ["python", "postgresql", "kafka"],
        "preferred": ["kubernetes"],
        "description": (
            "Lead the design of our event pipeline.\n\nRequirements\n- 8+ years of "
            "experience\n- Python, PostgreSQL and Kafka\n\nNice to have\n- Kubernetes"
        ),
    },
    {
        "company": "Contoso Analytics",
        "domain": "contoso.example",
        "title": "Machine Learning Engineer",
        "location": "Remote - US",
        "work_arrangement": WorkArrangement.REMOTE.value,
        "salary": (175_000, 215_000),
        "level": ExperienceLevel.SENIOR.value,
        "years": 5,
        "required": ["python", "pytorch"],
        "preferred": ["scikit-learn", "aws"],
        "description": (
            "Own model training and serving.\n\nRequirements\n- 5+ years of "
            "experience\n- Python and PyTorch\n\nNice to have\n- scikit-learn\n- AWS"
        ),
    },
]


def seed_jobs(db) -> int:
    created = 0
    now = datetime.now(timezone.utc)
    for index, item in enumerate(SAMPLE_JOBS):
        company = get_or_create_company(db, item["company"], item["domain"])
        fingerprint = compute_fingerprint(company.slug, item["title"], item["location"])
        exists = db.execute(
            select(Job).where(Job.fingerprint == fingerprint)
        ).scalar_one_or_none()
        if exists is not None:
            continue
        salary_min, salary_max = item["salary"]
        db.add(
            Job(
                company_id=company.id,
                external_id=f"seed-{index}",
                title=item["title"],
                description=item["description"],
                description_snapshot=item["description"],
                location=item["location"],
                street_address=item.get("street"),
                country="US",
                work_arrangement=item["work_arrangement"],
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency="USD",
                salary_period="year",
                experience_level=item["level"],
                min_years_experience=item["years"],
                technologies=[*item["required"], *item["preferred"]],
                required_skills=item["required"],
                preferred_skills=item["preferred"],
                requires_clearance=item.get("clearance"),
                date_posted=date.today() - timedelta(days=index),
                source_url=f"https://{item['domain']}/careers/{index}",
                apply_url=f"https://{item['domain']}/careers/{index}/apply",
                fingerprint=fingerprint,
                first_seen_at=now,
                last_verified_at=now,
                last_checked_at=now,
            )
        )
        created += 1
    db.flush()
    return created


def ensure_user(db, email: str, password: str, *, role: str, full_name: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_email_verified=True,
        onboarding_completed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(
        UserProfile(
            user_id=user.id,
            city="San Francisco",
            region="CA",
            country="US",
            current_title="Senior Software Engineer",
            years_of_experience=6,
        )
    )
    db.add(
        EligibilityProfile(
            user_id=user.id,
            work_authorization="citizen",
            authorized_countries=["US"],
            total_years_experience=6,
        )
    )
    db.add(
        JobPreferences(
            user_id=user.id,
            work_arrangements=[WorkArrangement.REMOTE.value, WorkArrangement.HYBRID.value],
            preferred_locations=["San Francisco, CA", "Remote"],
            desired_titles=["Backend Engineer", "Platform Engineer"],
            technologies=["python", "postgresql", "docker", "kubernetes"],
            experience_levels=[ExperienceLevel.SENIOR.value, ExperienceLevel.MID.value],
            match_threshold=30,
            max_days_since_posted=60,
        )
    )
    db.add(
        Resume(
            user_id=user.id,
            label="Seeded resume",
            original_filename="demo-resume.txt",
            content_type="text/plain",
            file_size=0,
            version=1,
            is_default=True,
            parse_status="parsed",
            parsed_at=datetime.now(timezone.utc),
            parsed_data={
                "full_name": full_name,
                "skills": ["python", "postgresql", "docker", "fastapi", "kubernetes", "aws"],
                "job_titles": ["Senior Software Engineer", "Backend Engineer"],
                "experience": [],
                "education": [],
                "certifications": [],
                "years_of_experience": 6,
            },
        )
    )
    db.flush()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the development database")
    parser.add_argument(
        "--with-demo-user", action="store_true", help="also create demo and admin accounts"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        sources = seed_default_sources(db)
        jobs = seed_jobs(db)
        if args.with_demo_user:
            ensure_user(
                db, DEMO_EMAIL, DEMO_PASSWORD, role=UserRole.USER.value, full_name="Demo User"
            )
            ensure_user(
                db, ADMIN_EMAIL, ADMIN_PASSWORD, role=UserRole.ADMIN.value, full_name="Admin User"
            )
        db.commit()

    print(f"Registered {sources} source(s) and created {jobs} sample job(s).")
    if args.with_demo_user:
        print(f"Demo user:  {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"Admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
