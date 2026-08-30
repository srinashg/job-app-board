"""Shared FastAPI dependencies: auth, current user, admin gate, pagination."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_ERROR
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise CREDENTIALS_ERROR from exc

    user = db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_ERROR
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated"
        )
    return user


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user


def require_onboarded(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Guard endpoints that only make sense once onboarding is finished."""
    if not user.is_onboarded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish onboarding before using job recommendations",
        )
    return user


class Pagination:
    """Shared ``limit``/``offset`` query parameters.

    Written with ``Query`` defaults rather than ``Annotated`` because this
    module uses postponed annotation evaluation, which FastAPI cannot resolve
    for ``Annotated`` metadata on a class ``__init__``.
    """

    def __init__(
        self,
        limit: int = Query(25, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> None:
        self.limit = limit
        self.offset = offset


CurrentUser = Annotated[User, Depends(get_current_user)]
OnboardedUser = Annotated[User, Depends(require_onboarded)]
AdminUser = Annotated[User, Depends(get_current_admin)]
DbSession = Annotated[Session, Depends(get_db)]
PageParams = Annotated[Pagination, Depends(Pagination)]
