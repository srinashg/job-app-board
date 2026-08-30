"""Skill/technology vocabulary used to extract structured signals from text.

Keeping this as data rather than a model keeps parsing and matching
deterministic and testable; V2 replaces the lookup with embeddings.
"""

from __future__ import annotations

import re

from app.services.text import normalize

#: canonical name -> aliases that should map onto it
TECHNOLOGY_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python3", "py"),
    "javascript": ("js", "ecmascript"),
    "typescript": ("ts",),
    "java": (),
    "go": ("golang",),
    "rust": (),
    "ruby": (),
    "php": (),
    "c#": ("csharp", "c sharp", "dotnet", ".net"),
    "c++": ("cpp", "c plus plus"),
    "c": (),
    "scala": (),
    "kotlin": (),
    "swift": (),
    "r": (),
    "sql": (),
    "bash": ("shell scripting",),
    "react": ("react.js", "reactjs"),
    "next.js": ("nextjs", "next js"),
    "vue": ("vue.js", "vuejs"),
    "angular": ("angularjs",),
    "svelte": ("sveltekit",),
    "node.js": ("nodejs", "node"),
    "django": (),
    "flask": (),
    "fastapi": (),
    "spring": ("spring boot", "springboot"),
    "rails": ("ruby on rails",),
    "express": ("express.js",),
    "graphql": (),
    "rest": ("rest api", "restful"),
    "grpc": (),
    "postgresql": ("postgres", "psql"),
    "mysql": (),
    "sqlite": (),
    "mongodb": ("mongo",),
    "redis": (),
    "elasticsearch": ("elastic search",),
    "cassandra": (),
    "dynamodb": (),
    "snowflake": (),
    "bigquery": (),
    "kafka": ("apache kafka",),
    "rabbitmq": (),
    "spark": ("apache spark", "pyspark"),
    "airflow": ("apache airflow",),
    "dbt": (),
    "hadoop": (),
    "aws": ("amazon web services",),
    "gcp": ("google cloud", "google cloud platform"),
    "azure": ("microsoft azure",),
    "docker": (),
    "kubernetes": ("k8s",),
    "terraform": (),
    "ansible": (),
    "jenkins": (),
    "github actions": ("gh actions",),
    "gitlab ci": ("gitlab-ci",),
    "circleci": (),
    "linux": (),
    "git": (),
    "pytest": (),
    "jest": (),
    "cypress": (),
    "playwright": (),
    "selenium": (),
    "pandas": (),
    "numpy": (),
    "scikit-learn": ("sklearn", "scikit learn"),
    "pytorch": ("torch",),
    "tensorflow": (),
    "sqlalchemy": (),
    "alembic": (),
    "prisma": (),
    "tailwind": ("tailwindcss", "tailwind css"),
    "html": ("html5",),
    "css": ("css3", "scss", "sass"),
    "figma": (),
    "jira": (),
    "tableau": (),
    "power bi": ("powerbi",),
    "excel": (),
    "salesforce": (),
    "sap": (),
}

SOFT_SKILLS: tuple[str, ...] = (
    "communication",
    "leadership",
    "mentoring",
    "collaboration",
    "problem solving",
    "project management",
    "stakeholder management",
    "agile",
    "scrum",
    "kanban",
    "code review",
    "technical writing",
    "public speaking",
    "customer facing",
    "cross functional",
)

#: Words that identify a job-title-like line in a resume.
TITLE_KEYWORDS: tuple[str, ...] = (
    "engineer",
    "developer",
    "scientist",
    "analyst",
    "manager",
    "designer",
    "architect",
    "administrator",
    "consultant",
    "specialist",
    "director",
    "lead",
    "intern",
    "researcher",
    "technician",
    "producer",
    "strategist",
    "recruiter",
    "accountant",
    "nurse",
    "teacher",
    "writer",
    "marketer",
)

_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in TECHNOLOGY_ALIASES.items():
    _ALIAS_LOOKUP[normalize(_canonical) or _canonical] = _canonical
    for _alias in _aliases:
        _ALIAS_LOOKUP[normalize(_alias) or _alias] = _canonical
for _soft in SOFT_SKILLS:
    _ALIAS_LOOKUP[normalize(_soft)] = _soft


def canonical_skill(value: str) -> str:
    """Map a free-text skill onto its canonical name, or clean it up in place."""
    key = normalize(value)
    if key in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[key]
    # Preserve punctuation-bearing names the normaliser would mangle (c++, c#).
    stripped = value.strip().lower()
    if stripped in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[stripped]
    return stripped


def canonical_skills(values: object) -> list[str]:
    """Canonicalise and de-duplicate a list of skills, preserving order."""
    if not isinstance(values, (list, tuple, set)):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        canonical = canonical_skill(value)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def _pattern_for(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    # Terms ending in punctuation (c++, c#, node.js) cannot use a trailing \b.
    trailing = r"\b" if term[-1].isalnum() else ""
    leading = r"\b" if term[0].isalnum() else ""
    return re.compile(leading + escaped + trailing, re.IGNORECASE)


_TERM_PATTERNS: list[tuple[re.Pattern[str], str]] = sorted(
    (
        (_pattern_for(term), canonical)
        for term, canonical in (
            *(
                (alias, canonical)
                for canonical, aliases in TECHNOLOGY_ALIASES.items()
                for alias in (canonical, *aliases)
            ),
            *((soft, soft) for soft in SOFT_SKILLS),
        )
    ),
    key=lambda item: -len(item[0].pattern),
)


def extract_technologies(text: str | None) -> list[str]:
    """Find every known technology/skill mentioned in a block of text."""
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pattern, canonical in _TERM_PATTERNS:
        if canonical in seen:
            continue
        if pattern.search(text):
            seen.add(canonical)
            found.append(canonical)
    return found


def looks_like_job_title(line: str) -> bool:
    lowered = line.lower()
    return any(keyword in lowered for keyword in TITLE_KEYWORDS)
