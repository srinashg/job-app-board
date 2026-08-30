"""Authentication and OAuth schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

MIN_PASSWORD_LENGTH = 10


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    accepted_terms: bool = Field(
        default=False, description="Must be true; recorded as a consent event."
    )

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must contain at least one letter")
        return value

    @field_validator("accepted_terms")
    @classmethod
    def _must_accept(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the terms of service to register")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str | None = None
    redirect_uri: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
