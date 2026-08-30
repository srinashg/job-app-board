"""SQLAlchemy models."""

from app.models.application import Application, ApplicationEvent, Contact
from app.models.job import Blacklist, Company, Job, JobSource
from app.models.recommendation import Batch, Recommendation
from app.models.resume import Resume
from app.models.user import (
    ConsentRecord,
    EligibilityProfile,
    JobPreferences,
    OAuthAccount,
    User,
    UserProfile,
)

__all__ = [
    "Application",
    "ApplicationEvent",
    "Batch",
    "Blacklist",
    "Company",
    "ConsentRecord",
    "Contact",
    "EligibilityProfile",
    "Job",
    "JobPreferences",
    "JobSource",
    "OAuthAccount",
    "Recommendation",
    "Resume",
    "User",
    "UserProfile",
]
