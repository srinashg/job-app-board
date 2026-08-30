"""Authentication: registration, login, refresh and OAuth 2.0 sign-in."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_state_token,
    hash_password,
    verify_password,
)
from app.models.enums import ConsentType
from app.models.user import ConsentRecord, EligibilityProfile, JobPreferences, OAuthAccount, User, UserProfile
from app.schemas.auth import (
    LoginRequest,
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.common import Message
from app.schemas.user import UserRead
from app.services.oauth import OAuthError, build_authorization_url, exchange_code, get_provider

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(str(user.id), {"role": user.role}),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _bootstrap_user(db: DbSession, user: User) -> None:
    """Give every new account the empty records onboarding will fill in."""
    db.add(UserProfile(user_id=user.id))
    db.add(EligibilityProfile(user_id=user.id))
    db.add(JobPreferences(user_id=user.id))
    db.flush()


def _record_consent(db: DbSession, user: User, consent_type: str, granted: bool) -> None:
    db.add(
        ConsentRecord(
            user_id=user.id,
            consent_type=consent_type,
            granted=granted,
            recorded_at=datetime.now(timezone.utc),
        )
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession) -> TokenPair:
    email = payload.email.lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    _bootstrap_user(db, user)
    _record_consent(db, user, ConsentType.TERMS_OF_SERVICE.value, True)
    _record_consent(db, user, ConsentType.PRIVACY_POLICY.value, True)
    db.flush()
    return _token_pair(user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    # Verify against a dummy hash when the user is unknown so the response time
    # does not reveal whether the address is registered.
    if user is None or not verify_password(payload.password, user.hashed_password or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated"
        )
    user.last_login_at = datetime.now(timezone.utc)
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    import uuid

    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    return _token_pair(user)


@router.get("/oauth/{provider}/authorize", response_model=OAuthAuthorizeResponse)
def oauth_authorize(provider: str) -> OAuthAuthorizeResponse:
    """Start the OAuth flow; the client stores ``state`` and echoes it back."""
    try:
        config = get_provider(provider)
        state = generate_state_token()
        return OAuthAuthorizeResponse(
            authorization_url=build_authorization_url(config, state), state=state
        )
    except OAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/oauth/{provider}/callback", response_model=TokenPair)
def oauth_callback(provider: str, payload: OAuthCallbackRequest, db: DbSession) -> TokenPair:
    try:
        config = get_provider(provider)
        identity = exchange_code(config, payload.code, payload.redirect_uri)
    except OAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    account = db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == identity.provider,
            OAuthAccount.provider_account_id == identity.account_id,
        )
    ).scalar_one_or_none()

    if account is not None:
        user = account.user
    else:
        user = db.execute(
            select(User).where(User.email == identity.email)
        ).scalar_one_or_none()
        is_new = user is None
        if user is None:
            user = User(
                email=identity.email,
                full_name=identity.full_name,
                is_email_verified=identity.email_verified,
            )
            db.add(user)
            db.flush()
            _bootstrap_user(db, user)
            _record_consent(db, user, ConsentType.TERMS_OF_SERVICE.value, True)
            _record_consent(db, user, ConsentType.PRIVACY_POLICY.value, True)
        db.add(
            OAuthAccount(
                user_id=user.id,
                provider=identity.provider,
                provider_account_id=identity.account_id,
                email=identity.email,
            )
        )
        db.flush()
        if is_new:
            db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated"
        )
    user.last_login_at = datetime.now(timezone.utc)
    return _token_pair(user)


@router.get("/me", response_model=UserRead)
def read_me(user: CurrentUser) -> User:
    return user


@router.post("/password", response_model=Message)
def change_password(payload: PasswordChangeRequest, user: CurrentUser) -> Message:
    if not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account signs in with a provider and has no password",
        )
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect"
        )
    user.hashed_password = hash_password(payload.new_password)
    return Message(detail="Password updated")
