"""Password hashing, JWT issuing/validation and at-rest field encryption."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta,
                  extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(subject, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode a JWT, raising ``ValueError`` when it is invalid or of the wrong type."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:  # pragma: no cover - message varies by cause
        raise ValueError("Could not validate credentials") from exc
    if expected_type and payload.get("type") != expected_type:
        raise ValueError(f"Expected a {expected_type} token")
    return payload


def generate_state_token() -> str:
    """Opaque value used as the OAuth 2.0 ``state`` parameter."""
    return secrets.token_urlsafe(32)


def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        # Deterministically derive a key from the app secret so development
        # installs work without extra setup. Production must set ENCRYPTION_KEY.
        digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_text(plaintext: str | None) -> str | None:
    """Encrypt personal free-text before it is written to the database."""
    if plaintext is None or plaintext == "":
        return plaintext
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(ciphertext: str | None) -> str | None:
    if ciphertext is None or ciphertext == "":
        return ciphertext
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Value predates encryption (or the key rotated); return it untouched
        # rather than losing the user's data.
        return ciphertext
