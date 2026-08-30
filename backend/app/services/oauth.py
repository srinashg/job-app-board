"""OAuth 2.0 authorization-code flow for third-party sign-in."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings


class OAuthError(RuntimeError):
    """Raised when the provider rejects the exchange or is not configured."""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    redirect_uri: str
    scope: str

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    account_id: str
    email: str
    full_name: str | None = None
    email_verified: bool = False


def get_provider(name: str) -> ProviderConfig:
    if name != "google":
        raise OAuthError(f"Unsupported OAuth provider: {name}")
    return ProviderConfig(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        authorize_url=settings.google_authorize_url,
        token_url=settings.google_token_url,
        userinfo_url=settings.google_userinfo_url,
        redirect_uri=settings.google_redirect_uri,
        scope="openid email profile",
    )


def build_authorization_url(provider: ProviderConfig, state: str) -> str:
    if not provider.is_configured:
        raise OAuthError(
            f"{provider.name} sign-in is not configured on this server. "
            "Set the client id and secret to enable it."
        )
    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{provider.authorize_url}?{urlencode(params)}"


def exchange_code(
    provider: ProviderConfig, code: str, redirect_uri: str | None = None
) -> OAuthIdentity:
    """Trade an authorization code for the provider's account identity."""
    if not provider.is_configured:
        raise OAuthError(f"{provider.name} sign-in is not configured on this server")

    payload = {
        "code": code,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "redirect_uri": redirect_uri or provider.redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            token_response = client.post(provider.token_url, data=payload)
            if token_response.status_code >= 400:
                raise OAuthError(
                    f"{provider.name} rejected the authorization code "
                    f"({token_response.status_code})"
                )
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise OAuthError(f"{provider.name} did not return an access token")

            userinfo_response = client.get(
                provider.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code >= 400:
                raise OAuthError(f"Could not read the {provider.name} profile")
            info = userinfo_response.json()
    except httpx.HTTPError as exc:
        raise OAuthError(f"Could not reach {provider.name}: {exc}") from exc

    email = info.get("email")
    account_id = info.get("sub") or info.get("id")
    if not email or not account_id:
        raise OAuthError(f"{provider.name} did not return an email address")

    return OAuthIdentity(
        provider=provider.name,
        account_id=str(account_id),
        email=email.lower(),
        full_name=info.get("name"),
        email_verified=bool(info.get("email_verified")),
    )
