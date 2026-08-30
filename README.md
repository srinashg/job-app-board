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
