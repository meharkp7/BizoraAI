"""Tests for auth tokens, membership, and project-ownership checks.

All tokens and secrets in this file are clearly-marked fakes minted
inline with the standard library; no identity provider is contacted.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from bizora.auth.dependencies import (
    configure_auth,
    get_current_principal,
    require_project_membership,
    reset_auth,
)
from bizora.auth.membership import (
    InMemoryMembershipStore,
    MembershipStore,
    SqlAlchemyMembershipStore,
)
from bizora.auth.tokens import (
    FakeStaticTokenStore,
    Hs256TokenVerifier,
    TokenAuthError,
    TokenVerifier,
    verify_hs256_token,
)
from bizora.contracts.auth import Principal, ProjectMembership, ProjectRole, role_satisfies
from bizora.core.errors import BizoraError, ErrorCode
from bizora.db.base import Base

FAKE_SECRET = "FAKE-TEST-ONLY-AUTH-SECRET"


@pytest.fixture(autouse=True)
def clean_auth_config() -> Iterator[None]:
    """Reset process-wide auth configuration around each test."""
    reset_auth()
    yield
    reset_auth()


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Create an isolated in-memory database for each test."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def mint_fake_jwt(
    *,
    secret: str = FAKE_SECRET,
    subject: str = "user-1",
    expires_in_seconds: int = 3600,
    algorithm: str = "HS256",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a clearly-fake HS256 JWT for tests (stdlib only)."""
    header = {"alg": algorithm, "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": int(time.time()) + expires_in_seconds,
        "jti": "fake-token-id",
    }
    if extra_claims:
        payload.update(extra_claims)

    def encode(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    signing_input = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    encoded_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{signing_input}.{encoded_sig}"


def bearer(token: str) -> HTTPAuthorizationCredentials:
    """Build bearer credentials as FastAPI would parse them."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_verify_accepts_valid_fake_token() -> None:
    principal = verify_hs256_token(mint_fake_jwt(), FAKE_SECRET)

    assert isinstance(principal, Principal)
    assert principal.user_id == "user-1"
    assert principal.expires_at is not None
    assert principal.token_id == "fake-token-id"


def test_verify_rejects_tampered_expired_and_confused_tokens() -> None:
    valid = mint_fake_jwt()
    tampered = valid[:-2] + ("AA" if not valid.endswith("AA") else "BB")

    with pytest.raises(TokenAuthError):
        verify_hs256_token(tampered, FAKE_SECRET)
    with pytest.raises(TokenAuthError):
        verify_hs256_token(mint_fake_jwt(), "WRONG-FAKE-SECRET")
    with pytest.raises(TokenAuthError):
        verify_hs256_token(mint_fake_jwt(expires_in_seconds=-3600), FAKE_SECRET)
    with pytest.raises(TokenAuthError):
        verify_hs256_token(mint_fake_jwt(algorithm="none"), FAKE_SECRET)
    with pytest.raises(TokenAuthError):
        verify_hs256_token("not-a-token", FAKE_SECRET)
    with pytest.raises(TokenAuthError):
        verify_hs256_token(mint_fake_jwt(), "")
    with pytest.raises(TokenAuthError):
        verify_hs256_token(
            mint_fake_jwt(extra_claims={"exp": None}), FAKE_SECRET
        )


def test_verify_errors_never_echo_token_or_secret() -> None:
    token = mint_fake_jwt()
    with pytest.raises(TokenAuthError) as exc_info:
        verify_hs256_token(token + "tamper", FAKE_SECRET)
    assert token not in str(exc_info.value)
    assert FAKE_SECRET not in str(exc_info.value)


def test_verifier_protocol_and_backends() -> None:
    explicit = Hs256TokenVerifier(secret=FAKE_SECRET)
    assert isinstance(explicit, TokenVerifier)
    assert explicit.verify(mint_fake_jwt()).user_id == "user-1"

    fake_store = FakeStaticTokenStore()
    assert isinstance(fake_store, TokenVerifier)
    fake_store.register("FAKE-STATIC-TOKEN", Principal(user_id="user-9"))
    assert fake_store.verify("FAKE-STATIC-TOKEN").user_id == "user-9"
    with pytest.raises(TokenAuthError):
        fake_store.verify("unknown-fake-token")


def test_role_ranking_orders_weakest_to_strongest() -> None:
    assert role_satisfies(ProjectRole.OWNER, ProjectRole.VIEWER)
    assert role_satisfies(ProjectRole.EDITOR, ProjectRole.EDITOR)
    assert not role_satisfies(ProjectRole.VIEWER, ProjectRole.EDITOR)
    assert not role_satisfies(ProjectRole.EDITOR, ProjectRole.OWNER)


def test_in_memory_store_tracks_fake_membership() -> None:
    store = InMemoryMembershipStore()
    assert isinstance(store, MembershipStore)

    assert store.get_role("project-1", "user-1") is None
    store.add_member(
        ProjectMembership(
            project_id="project-1", user_id="user-1", role=ProjectRole.EDITOR
        )
    )
    assert store.get_role("project-1", "user-1") == ProjectRole.EDITOR
    assert store.get_role("project-2", "user-1") is None
    store.remove_member("project-1", "user-1")
    assert store.get_role("project-1", "user-1") is None


def test_sqlalchemy_store_persists_membership(engine: Engine) -> None:
    def factory() -> Session:
        return Session(engine)

    store = SqlAlchemyMembershipStore(factory)
    assert isinstance(store, MembershipStore)

    assert store.get_role("project-1", "user-1") is None
    store.add_member(
        ProjectMembership(
            project_id="project-1", user_id="user-1", role=ProjectRole.OWNER
        )
    )
    assert store.get_role("project-1", "user-1") == ProjectRole.OWNER

    with pytest.raises(BizoraError) as exc_info:
        store.add_member(
            ProjectMembership(
                project_id="project-1", user_id="user-1", role=ProjectRole.VIEWER
            )
        )
    assert exc_info.value.code == ErrorCode.RESOURCE_CONFLICT

    store.remove_member("project-1", "user-1")
    assert store.get_role("project-1", "user-1") is None


def test_principal_dependency_rejects_missing_and_bad_tokens() -> None:
    configure_auth(FakeStaticTokenStore(), InMemoryMembershipStore())

    with pytest.raises(HTTPException) as missing:
        asyncio.run(get_current_principal(None))
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as bad:
        asyncio.run(get_current_principal(bearer("unknown-fake-token")))
    assert bad.value.status_code == 401


def test_principal_dependency_fails_closed_when_unconfigured() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_principal(bearer("whatever")))
    assert exc_info.value.status_code == 500


def test_principal_dependency_resolves_fake_token() -> None:
    store = FakeStaticTokenStore()
    store.register("FAKE-STATIC-TOKEN", Principal(user_id="user-1"))
    configure_auth(store, InMemoryMembershipStore())

    principal = asyncio.run(get_current_principal(bearer("FAKE-STATIC-TOKEN")))

    assert principal.user_id == "user-1"


def test_project_membership_grants_members_only() -> None:
    store = FakeStaticTokenStore()
    store.register("FAKE-MEMBER", Principal(user_id="member-1"))
    store.register("FAKE-OUTSIDER", Principal(user_id="outsider-1"))
    memberships = InMemoryMembershipStore()
    memberships.add_member(
        ProjectMembership(
            project_id="project-1", user_id="member-1", role=ProjectRole.VIEWER
        )
    )
    configure_auth(store, memberships)
    check = require_project_membership("project-1")

    member = asyncio.run(get_current_principal(bearer("FAKE-MEMBER")))
    assert asyncio.run(check(member)).user_id == "member-1"

    outsider = asyncio.run(get_current_principal(bearer("FAKE-OUTSIDER")))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check(outsider))
    assert exc_info.value.status_code == 403


def test_project_membership_enforces_allowed_roles() -> None:
    store = FakeStaticTokenStore()
    store.register("FAKE-VIEWER", Principal(user_id="viewer-1"))
    store.register("FAKE-OWNER", Principal(user_id="owner-1"))
    memberships = InMemoryMembershipStore()
    memberships.add_member(
        ProjectMembership(
            project_id="project-1", user_id="viewer-1", role=ProjectRole.VIEWER
        )
    )
    memberships.add_member(
        ProjectMembership(
            project_id="project-1", user_id="owner-1", role=ProjectRole.OWNER
        )
    )
    configure_auth(store, memberships)
    owners_only = require_project_membership("project-1", ProjectRole.OWNER)

    viewer = asyncio.run(get_current_principal(bearer("FAKE-VIEWER")))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(owners_only(viewer))
    assert exc_info.value.status_code == 403

    owner = asyncio.run(get_current_principal(bearer("FAKE-OWNER")))
    assert asyncio.run(owners_only(owner)).user_id == "owner-1"


def test_project_membership_is_scoped_to_one_project() -> None:
    store = FakeStaticTokenStore()
    store.register("FAKE-MEMBER", Principal(user_id="member-1"))
    memberships = InMemoryMembershipStore()
    memberships.add_member(
        ProjectMembership(
            project_id="project-1", user_id="member-1", role=ProjectRole.OWNER
        )
    )
    configure_auth(store, memberships)

    member = asyncio.run(get_current_principal(bearer("FAKE-MEMBER")))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_project_membership("project-2")(member))
    assert exc_info.value.status_code == 403
