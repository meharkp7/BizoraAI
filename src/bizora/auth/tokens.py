"""Bearer-token verification without third-party JWT libraries.

Production tokens are HS256 JWTs minted by the identity provider and
verified here with a shared secret from ``BIZORA_AUTH_SECRET``.
Verification fails closed: unknown algorithms, missing subjects, and
expired tokens are all rejected, and error messages never echo tokens
or secrets.
"""

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from bizora.contracts.auth import Principal


class TokenAuthError(Exception):
    """Raised when a bearer token cannot be authenticated."""


@runtime_checkable
class TokenVerifier(Protocol):
    """Interface implemented by bearer-token verifiers."""

    def verify(self, token: str) -> Principal:
        """Return the principal for a token or raise TokenAuthError."""
        ...


def _b64url_decode(segment: str) -> bytes:
    """Decode one base64url segment, tolerating missing padding."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise TokenAuthError("Malformed token encoding.") from exc


def verify_hs256_token(
    token: str,
    secret: str,
    *,
    now: datetime | None = None,
    leeway_seconds: int = 30,
) -> Principal:
    """Verify an HS256 JWT and return its principal."""
    if not secret:
        raise TokenAuthError("Token verification is not configured.")
    if leeway_seconds < 0:
        raise ValueError("leeway_seconds must be non-negative.")
    moment = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("Verification timestamps must be timezone-aware.")

    parts = token.split(".")
    if len(parts) != 3:
        raise TokenAuthError("Malformed token structure.")
    header_segment, payload_segment, signature_segment = parts
    try:
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, TokenAuthError) as exc:
        raise TokenAuthError("Malformed token JSON.") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise TokenAuthError("Unsupported token algorithm.")
    if not isinstance(payload, dict):
        raise TokenAuthError("Malformed token claims.")

    expected = hmac.new(
        secret.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided = _b64url_decode(signature_segment)
    except TokenAuthError as exc:
        raise TokenAuthError("Malformed token signature.") from exc
    if not hmac.compare_digest(expected, provided):
        raise TokenAuthError("Invalid token signature.")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject or len(subject) > 128:
        raise TokenAuthError("Token has no usable subject.")
    expires_raw = payload.get("exp")
    if not isinstance(expires_raw, (int, float)) or isinstance(expires_raw, bool):
        raise TokenAuthError("Token has no usable expiry.")
    expires_at = datetime.fromtimestamp(float(expires_raw), tz=UTC)
    if moment > expires_at + timedelta(seconds=leeway_seconds):
        raise TokenAuthError("Token has expired.")
    token_id = payload.get("jti")
    return Principal(
        user_id=subject,
        expires_at=expires_at,
        token_id=token_id if isinstance(token_id, str) and token_id else None,
    )


class Hs256TokenVerifier:
    """Shared-secret JWT verifier reading its secret from the environment."""

    ENV_VAR = "BIZORA_AUTH_SECRET"

    def __init__(self, secret: str | None = None) -> None:
        self._secret = secret if secret is not None else os.environ.get(self.ENV_VAR, "")

    def verify(self, token: str) -> Principal:
        """Verify a token against the configured secret."""
        return verify_hs256_token(token, self._secret)


class FakeStaticTokenStore:
    """CLEARLY-MARKED TEST FAKE: static token-to-principal mapping.

    Never use outside tests and local development: tokens are bearer
    strings with no cryptography, held in process memory.
    """

    def __init__(self) -> None:
        self._principals: dict[str, Principal] = {}

    def register(self, token: str, principal: Principal) -> None:
        """Bind a fake token to a principal for one test."""
        if not token:
            raise ValueError("Fake tokens must be non-empty.")
        self._principals[token] = principal

    def verify(self, token: str) -> Principal:
        """Return the bound principal or raise TokenAuthError."""
        try:
            return self._principals[token]
        except KeyError:
            raise TokenAuthError("Unknown test token.") from None
