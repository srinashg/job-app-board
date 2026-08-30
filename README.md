# job-app-board

A job-search execution app that reduces endless browsing by giving users five relevant jobs at a time. Users resolve the batch by applying, legitimately skipping, or marking a job unavailable before receiving the next set.

## **MVP**

### Features — implementation order
1. Authentication, onboarding, profile, eligibility rules, and job preferences.
2. Resume upload and parsing with editable extracted skills, experience, education, certifications, and job titles.
3. Resume version manager for uploading, renaming, deleting, and selecting the resume used for each application.
4. Job fetching from legitimate company career sites/ATS sources, storing title, company, description, location, work arrangement, address for hybrid/on-site roles, salary if available, date posted, source URL, and last verified date.
5. Job freshness and duplicate protection: detect duplicates, re-check listings, mark closed jobs, and avoid recommending the same job twice.
6. Job matching using hard eligibility rules plus skills, experience, title, location, technologies, and user preferences. Show match score with strong, partial, and missing qualifications.
7. Five-job batch system: show five active recommendations, track completion, and unlock the next batch after all five are resolved.
8. Skip system with reasons such as not qualified, already applied, closed, location, salary, sponsorship, clearance, experience level, or not interested. Replace skipped/closed jobs when appropriate.
9. Preference filter panel for work setup, location/radius, salary, job title, experience level, technologies, industry, date posted, match threshold, and excluded companies.
10. Job details page with match explanation, saved job-description snapshot, company/location details, official source, Apply, Skip, and Save actions.
11. Application tracker with Todo, Applied, Interview, Offer, Rejected, Withdrawn, Skipped, and Closed statuses.
12. Application history storing company, position, location, work setup/address or Remote, application URL/date, status, resume used, job-description snapshot, notes, and recruiter/contact information.
13. Basic dashboard for applications, responses, interviews, offers, pipeline counts, and response rate.
14. Lightweight `/admin/jobs` page to inspect, disable, mark stale/duplicate/scam, or blacklist jobs, companies, and domains.
15. Privacy/account controls for resume deletion, account deletion, consent, and secure handling of personal data.

### Tech Stack
- React + Next.js + TypeScript
- Python + FastAPI
- OAuth 2.0 + JWT
- PostgreSQL
- SQLAlchemy + Alembic
- REST APIs
- Docker
- Playwright for job-source automation/verification
- Pytest for backend testing

### Status

The MVP is implemented. All fifteen features above are built end to end, with
155 backend tests covering them.

## Running it

### With Docker

```bash
cp .env.example .env      # then edit SECRET_KEY and ENCRYPTION_KEY
docker compose up --build
```

The web app is on <http://localhost:3000>, the API on <http://localhost:8000>,
and the interactive API docs on <http://localhost:8000/docs>. Migrations run
automatically when the API container boots.

### Locally

```bash
make install     # backend venv + frontend node_modules
make migrate     # apply Alembic migrations
make seed        # sample jobs plus demo and admin accounts
make api         # backend on :8000
make web         # frontend on :3000 (separate terminal)
```

`make seed` creates `demo@example.com` / `demo-password-1` and
`admin@example.com` / `admin-password-1`. Change or remove them before
deploying anywhere real.

Requires Python 3.11+, Node 22+ and PostgreSQL 16.

### Tests

```bash
make test        # pytest, needs a reachable Postgres
make lint        # frontend typecheck
```

The suite uses a real PostgreSQL database (the schema is JSONB-heavy, so
SQLite would not exercise the same code). Point it at one with
`TEST_DATABASE_URL`; it defaults to a `jobboard_test` database on localhost.

## How it is put together

```
backend/
  app/
    api/v1/      REST endpoints, one module per feature area
    core/        configuration, JWT and password handling, dependencies
    db/          declarative base, engine, session
    models/      SQLAlchemy models
    schemas/     Pydantic request/response contracts
    services/    the logic: matching, batching, parsing, ingestion, dedupe
      ingest/    one connector per ATS, plus the Playwright verifier
    alembic/     migrations
  scripts/seed.py
  tests/         pytest suite, one module per feature area
frontend/
  app/           Next.js App Router pages
  components/    shared UI
  lib/           typed API client, auth context, formatting
```

### Design notes

**Matching** is deterministic, not learned. Hard eligibility rules (sponsorship,
clearance, citizenship, excluded companies, work setup, salary floor, posting
age) gate a job out entirely; the remaining jobs get a weighted score across
skills, technologies, title, experience, location and salary. Every point is
traceable to a qualification line the user can read, and a signal with no data
carries no weight rather than scoring zero.

**Batches** hand out five jobs and refuse the next set until all five are
applied to, skipped or marked unavailable. A `(user_id, job_id)` uniqueness
constraint plus candidate-pool exclusion means a job is never recommended
twice. Saving a job deliberately does not resolve it.

**Job freshness** combines a fingerprint (company + normalised title +
normalised location) with a title/description similarity check to catch the
same role cross-posted through two sources. Listings are re-verified on a
schedule; Playwright renders the page because career sites often keep the URL
alive and swap the body for a "no longer accepting applications" notice that an
HTTP status check cannot see.

**Personal data** — phone, home address and recruiter contact details — is
encrypted with Fernet before it reaches the database. Deleting a resume removes
the stored bytes, not just a row, and deleting an account cascades through
every table and purges the files.

Listing re-verification uses Playwright when `PLAYWRIGHT_ENABLED=true` and a
browser is installed (`playwright install chromium`, or uncomment the line in
`backend/Dockerfile`). Without it the verifier falls back to an HTTP check,
which catches removed listings but not pages that stay up with a "no longer
accepting applications" body.

### Job sources

Ingestion runs against public ATS APIs — Greenhouse, Lever and Ashby — which
publish their boards for exactly this purpose. Adding a provider means writing
one connector implementing `fetch` and `is_open` and registering it in
`app/services/ingest/__init__.py`.

## **V2**

### Features — implementation order
1. AI resume tailoring that only reorganizes or rewrites existing experience and never invents qualifications.
2. Application packet with recommended resume, suggested changes, saved job description, company overview, skills to emphasize, gaps, and optional cover letter.
3. Tailored resume copies linked to individual applications.
4. Saved job-filter presets for different search strategies.
5. Follow-up reminders for submitted applications.
6. Interview workspace with job description, submitted resume, recruiter, interview date/stage, notes, questions, company research, and preparation checklist.
7. Company research panel with company overview, industry, size, products, career site, recent developments, and relevant technologies.
8. Search intelligence that learns from apply/skip behavior and improves future job ranking.
9. Better location intelligence with distance and estimated commute filtering using approximate location or ZIP code.

### Additional Tech Stack
- LLM API integration
- Vector embeddings + pgvector for semantic job-resume matching
- Geocoding/maps API
- Redis + Celery for scheduled follow-ups and recommendation updates

## **Future**

### Features — implementation order
1. Full AI interview preparation using the saved job description and submitted resume.
2. Recruiter/contact CRM with communication notes and follow-up tracking.
3. Email integration to detect application confirmations, rejections, and interview invitations and suggest status updates.
4. Calendar integration for interviews and upcoming events.
5. Advanced job-search analytics by role, company, technology, response rate, interview rate, and offer rate.
6. Resume performance analytics comparing application, response, and interview results across resume versions.
7. Multi-user moderation with user reports, scam/broken-link review, source quality controls, moderation queues, user management, and audit logs.
8. Browser extension to capture outside job postings and run them through the app's matching workflow.
9. Mobile app.

### Additional Tech Stack
- Gmail API / Microsoft Graph
- Google Calendar API / Microsoft Graph Calendar
- Browser Extension APIs
- Mobile framework such as React Native
