"""Imports every model so Alembic autogenerate sees the full metadata."""

from app.db.base_class import Base  # noqa: F401
from app.models.application import (  # noqa: F401
    Application,
    ApplicationEvent,
    Contact,
)
from app.models.job import (  # noqa: F401
    Blacklist,
    Company,
    Job,
    JobSource,
)
from app.models.recommendation import (  # noqa: F401
    Batch,
    Recommendation,
)
from app.models.resume import Resume  # noqa: F401
from app.models.user import (  # noqa: F401
    ConsentRecord,
    EligibilityProfile,
    JobPreferences,
    OAuthAccount,
    User,
    UserProfile,
)

__all__ = ["Base"]
