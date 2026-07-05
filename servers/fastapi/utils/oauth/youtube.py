"""Google OAuth PKCE helpers for YouTube Data API v3 uploads.

This module intentionally does **not** start a local callback server. The user's
browser is sent to Google's authorization URL; Google redirects to a backend
endpoint (``/api/v1/video-studio/youtube/auth/callback``) which is reachable
through the normal nginx reverse proxy. Tokens are stored in the database.
"""
import base64
import hashlib
import logging
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx

LOGGER = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"

DEFAULT_REDIRECT_URI = "http://localhost:8000/api/v1/video-studio/youtube/auth/callback"


def _get_redirect_uri() -> str:
    return os.environ.get("YOUTUBE_REDIRECT_URI", DEFAULT_REDIRECT_URI)


def _generate_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


class AuthorizationFlow:
    """Lightweight container for a single OAuth flow."""

    def __init__(self, client_id: str, redirect_uri: str):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.verifier, self.challenge = _generate_pkce()
        self.state = secrets.token_hex(16)

    @property
    def url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPE,
            "state": self.state,
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"


def create_authorization_flow(
    client_id: str,
    redirect_uri: Optional[str] = None,
) -> AuthorizationFlow:
    """Generate a PKCE authorization URL for YouTube upload scope."""
    return AuthorizationFlow(
        client_id=client_id,
        redirect_uri=redirect_uri or _get_redirect_uri(),
    )


def exchange_authorization_code(
    code: str,
    verifier: str,
    client_id: str,
    redirect_uri: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> dict:
    """Exchange an authorization code for Google tokens."""
    data: dict[str, Optional[str]] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri or _get_redirect_uri(),
        "code_verifier": verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret

    response = httpx.post(TOKEN_URL, data=data, timeout=30)
    LOGGER.debug("[youtube_oauth] token exchange status %s", response.status_code)
    response.raise_for_status()
    return response.json()


def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: Optional[str] = None,
) -> dict:
    """Refresh a Google access token."""
    data: dict[str, Optional[str]] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    response = httpx.post(TOKEN_URL, data=data, timeout=30)
    response.raise_for_status()
    return response.json()
