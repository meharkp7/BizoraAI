"""API tests for project collaboration invites."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_accounts_api import auth_headers, register

from bizora.auth.dependencies import configure_auth, reset_auth
from bizora.auth.membership import InMemoryMembershipStore
from bizora.auth.tokens import Hs256TokenVerifier, TokenAuthError, verify_hs256_token
from bizora.contracts.auth import ProjectRole
from bizora.core.errors import BizoraError, ErrorCode
from bizora.core.invites import InviteService, mint_invite_token, verify_invite_token
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app

TEST_SECRET = "TEST-ONLY-AUTH-SECRET"


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Provide a test client with auth configured and an isolated database."""
    monkeypatch.setenv("BIZORA_AUTH_SECRET", TEST_SECRET)
    configure_auth(Hs256TokenVerifier(TEST_SECRET), InMemoryMembershipStore())
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        reset_auth()
        engine.dispose()


def _invite(client: TestClient, token: str, email: str = "guest@example.com") -> dict:
    response = client.post(
        "/api/v1/projects/demo-proj/invites",
        headers=auth_headers(token),
        json={"email": email, "role": "editor"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_invite_returns_one_time_token(authed_client: TestClient) -> None:
    owner = register(authed_client)
    body = _invite(authed_client, owner["token"])

    assert body["invite"]["email"] == "guest@example.com"
    assert body["invite"]["role"] == "editor"
    assert body["invite"]["status"] == "pending"
    assert body["invite"]["created_by"] == owner["user"]["user_id"]
    assert body["token"]
    invite_id, project_id = verify_invite_token(token=body["token"], secret=TEST_SECRET)
    assert invite_id == body["invite"]["invite_id"]
    assert project_id == "demo-proj"


def test_invite_routes_require_auth(authed_client: TestClient) -> None:
    assert authed_client.get("/api/v1/projects/demo-proj/invites").status_code == 401
    created = authed_client.post(
        "/api/v1/projects/demo-proj/invites",
        json={"email": "guest@example.com"},
    )
    assert created.status_code == 401


def test_create_invite_rejects_bad_email_and_conflicts(authed_client: TestClient) -> None:
    owner = register(authed_client)
    bad = authed_client.post(
        "/api/v1/projects/demo-proj/invites",
        headers=auth_headers(owner["token"]),
        json={"email": "not-an-email"},
    )
    assert bad.status_code == 422

    _invite(authed_client, owner["token"])
    duplicate = authed_client.post(
        "/api/v1/projects/demo-proj/invites",
        headers=auth_headers(owner["token"]),
        json={"email": "GUEST@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_list_invites_never_shows_tokens(authed_client: TestClient) -> None:
    owner = register(authed_client)
    created = _invite(authed_client, owner["token"])
    response = authed_client.get(
        "/api/v1/projects/demo-proj/invites",
        headers=auth_headers(owner["token"]),
    )

    assert response.status_code == 200
    invites = response.json()
    assert [invite["invite_id"] for invite in invites] == [created["invite"]["invite_id"]]
    assert "token" not in invites[0]


def test_accept_invite_records_membership(authed_client: TestClient) -> None:
    owner = register(authed_client)
    guest = register(authed_client, email="guest@example.com")
    created = _invite(authed_client, owner["token"])
    invite_id = created["invite"]["invite_id"]

    accepted = authed_client.post(
        f"/api/v1/projects/demo-proj/invites/{invite_id}/accept",
        headers=auth_headers(guest["token"]),
        json={"token": created["token"]},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    again = authed_client.post(
        f"/api/v1/projects/demo-proj/invites/{invite_id}/accept",
        headers=auth_headers(guest["token"]),
        json={"token": created["token"]},
    )
    assert again.status_code == 409


def test_accept_invite_rejects_forged_and_mismatched_tokens(
    authed_client: TestClient,
) -> None:
    owner = register(authed_client)
    guest = register(authed_client, email="guest@example.com")
    created = _invite(authed_client, owner["token"])
    invite_id = created["invite"]["invite_id"]

    forged = authed_client.post(
        f"/api/v1/projects/demo-proj/invites/{invite_id}/accept",
        headers=auth_headers(guest["token"]),
        json={"token": "forged.payload"},
    )
    assert forged.status_code == 422

    other = _invite(authed_client, owner["token"], email="other@example.com")
    mismatched = authed_client.post(
        f"/api/v1/projects/demo-proj/invites/{invite_id}/accept",
        headers=auth_headers(guest["token"]),
        json={"token": other["token"]},
    )
    assert mismatched.status_code == 422


def test_invite_token_never_verifies_as_login_token() -> None:
    token = mint_invite_token(invite_id="inv-1", project_id="proj-1", secret=TEST_SECRET)
    with pytest.raises(TokenAuthError):
        verify_hs256_token(token, TEST_SECRET)


def test_revoke_invite_blocks_accept(authed_client: TestClient) -> None:
    owner = register(authed_client)
    guest = register(authed_client, email="guest@example.com")
    created = _invite(authed_client, owner["token"])
    invite_id = created["invite"]["invite_id"]

    revoked = authed_client.delete(
        f"/api/v1/projects/demo-proj/invites/{invite_id}",
        headers=auth_headers(owner["token"]),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    late = authed_client.post(
        f"/api/v1/projects/demo-proj/invites/{invite_id}/accept",
        headers=auth_headers(guest["token"]),
        json={"token": created["token"]},
    )
    assert late.status_code == 409


def test_unknown_invite_is_404(authed_client: TestClient) -> None:
    owner = register(authed_client)
    missing = authed_client.delete(
        "/api/v1/projects/demo-proj/invites/nope",
        headers=auth_headers(owner["token"]),
    )
    assert missing.status_code == 404


def test_expired_invite_rejects_accept() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = InMemoryMembershipStore()
    with Session(engine) as session:
        record, token = InviteService(
            session, store, secret=TEST_SECRET, now=datetime.now(UTC) - timedelta(days=8)
        ).create_invite(
            project_id="proj-1",
            email="guest@example.com",
            role=ProjectRole.VIEWER,
            created_by="owner-1",
        )
        with pytest.raises(BizoraError) as exc_info:
            InviteService(session, store, secret=TEST_SECRET).accept_invite(
                project_id="proj-1",
                invite_id=record.id,
                token=token,
                user_id="guest-1",
            )
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST
    engine.dispose()
