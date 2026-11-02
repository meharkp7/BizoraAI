"""Project collaboration invites on top of membership storage.

An invite is a bearer token emailed (or linked) to a collaborator:
whoever presents a valid, unexpired, pending token while
authenticated joins the project at the invited role. Tokens use a
domain-separated HMAC over the invite id and project id, so they
never verify as login JWTs even though they share the auth secret.
Only a SHA-256 hash of each token is persisted; the token itself is
shown once at creation.

Documented limits: any authenticated user may invite (no role
gating yet), and the invited email is advisory — the accepting
user's own account joins, regardless of address match.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from bizora.auth.membership import MembershipStore
from bizora.contracts.auth import (
    InviteStatus,
    ProjectMembership,
    ProjectRole,
)
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db import repository
from bizora.db.models import ProjectInvite

INVITE_LIFETIME = timedelta(days=7)
_SIGNING_DOMAIN = b"bizora-project-invite-v1"
_PLAIN_EMAIL_ERROR = "Invite email must look like name@example.com."


def _b64url_encode(raw: bytes) -> str:
    """Encode bytes as unpadded base64url."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Decode one base64url segment, tolerating missing padding."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.") from exc


def mint_invite_token(*, invite_id: str, project_id: str, secret: str) -> str:
    """Mint a domain-separated bearer token for one invite."""
    if not secret:
        raise BizoraError(
            ErrorCode.INVALID_CONFIGURATION,
            "Invite signing is not configured.",
        )
    payload = _b64url_encode(
        json.dumps({"invite_id": invite_id, "project_id": project_id}).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), _SIGNING_DOMAIN + payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64url_encode(signature)}"


def verify_invite_token(*, token: str, secret: str) -> tuple[str, str]:
    """Verify a token signature; return (invite_id, project_id)."""
    if not secret:
        raise BizoraError(
            ErrorCode.INVALID_CONFIGURATION,
            "Invite signing is not configured.",
        )
    parts = token.split(".")
    if len(parts) != 2:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.")
    payload_segment, signature_segment = parts
    expected = hmac.new(
        secret.encode("utf-8"), _SIGNING_DOMAIN + payload_segment.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        provided = _b64url_decode(signature_segment)
    except BizoraError as exc:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.") from exc
    if not hmac.compare_digest(expected, provided):
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is invalid.")
    try:
        payload = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, UnicodeDecodeError, BizoraError) as exc:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.") from exc
    if not isinstance(payload, dict):
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.")
    invite_id = payload.get("invite_id")
    project_id = payload.get("project_id")
    if not isinstance(invite_id, str) or not invite_id:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.")
    if not isinstance(project_id, str) or not project_id:
        raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is malformed.")
    return invite_id, project_id


def hash_invite_token(token: str) -> str:
    """Return the persisted SHA-256 hash of an invite token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    """Lowercase and validate an invite email address."""
    normalized = email.strip().lower()
    local, separator, domain = normalized.partition("@")
    if not separator or not local or "." not in domain:
        raise BizoraError(ErrorCode.INVALID_REQUEST, _PLAIN_EMAIL_ERROR)
    return normalized


def _aware(value: datetime) -> datetime:
    """Return a timezone-aware timestamp, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class InviteService:
    """Create, list, accept, and revoke project invites."""

    def __init__(
        self,
        session: Session,
        store: MembershipStore,
        *,
        secret: str,
        now: datetime | None = None,
    ) -> None:
        self._session = session
        self._store = store
        self._secret = secret
        self._now = _aware(now) if now is not None else datetime.now(UTC)

    def create_invite(
        self,
        *,
        project_id: str,
        email: str,
        role: ProjectRole,
        created_by: str,
    ) -> tuple[ProjectInvite, str]:
        """Create a pending invite and return it with its one-time token."""
        normalized = _normalize_email(email)
        existing = repository.pending_invite_for_email(
            self._session, project_id=project_id, email=normalized
        )
        if existing is not None:
            raise BizoraError(
                ErrorCode.RESOURCE_CONFLICT,
                "That email already has a pending invite to this project.",
                details={"invite_id": existing.id},
            )
        invite_id = uuid.uuid4().hex
        token = mint_invite_token(invite_id=invite_id, project_id=project_id, secret=self._secret)
        record = repository.save_project_invite(
            self._session,
            invite_id=invite_id,
            project_id=project_id,
            email=normalized,
            role=role.value,
            token_hash=hash_invite_token(token),
            created_by=created_by,
            now=self._now,
            expires_at=self._now + INVITE_LIFETIME,
        )
        self._session.commit()
        return record, token

    def list_invites(self, *, project_id: str, limit: int = 50) -> list[ProjectInvite]:
        """List one project's invites, newest first."""
        return repository.list_project_invites(self._session, project_id=project_id, limit=limit)

    def accept_invite(
        self,
        *,
        project_id: str,
        invite_id: str,
        token: str,
        user_id: str,
    ) -> ProjectInvite:
        """Accept an invite, recording membership for the caller."""
        claimed_id, claimed_project = verify_invite_token(token=token, secret=self._secret)
        if claimed_id != invite_id or claimed_project != project_id:
            raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token does not match this invite.")
        record = repository.get_project_invite(
            self._session, project_id=project_id, invite_id=invite_id
        )
        if record is None:
            raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Invite not found.")
        if record.token_hash != hash_invite_token(token):
            raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite token is invalid.")
        if record.status != InviteStatus.PENDING.value:
            raise BizoraError(
                ErrorCode.RESOURCE_CONFLICT,
                f"Invite is already {record.status}.",
            )
        if _aware(record.expires_at) < self._now:
            raise BizoraError(ErrorCode.INVALID_REQUEST, "Invite has expired.")
        self._store.add_member(
            ProjectMembership(project_id=project_id, user_id=user_id, role=ProjectRole(record.role))
        )
        record.status = InviteStatus.ACCEPTED.value
        record.accepted_by = user_id
        self._session.commit()
        return record

    def revoke_invite(self, *, project_id: str, invite_id: str) -> ProjectInvite:
        """Revoke a pending invite; accepted invites stay accepted."""
        record = repository.get_project_invite(
            self._session, project_id=project_id, invite_id=invite_id
        )
        if record is None:
            raise BizoraError(ErrorCode.RESOURCE_NOT_FOUND, "Invite not found.")
        if record.status != InviteStatus.PENDING.value:
            raise BizoraError(
                ErrorCode.RESOURCE_CONFLICT,
                f"Invite is already {record.status}.",
            )
        record.status = InviteStatus.REVOKED.value
        self._session.commit()
        return record
