"""API tests for JWT accounts, paper libraries, and notes."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_papers_api import FakePaperProvider, make_pdf_bytes

from bizora.api import get_baseten_provider
from bizora.auth.dependencies import configure_auth, reset_auth
from bizora.auth.membership import InMemoryMembershipStore
from bizora.auth.passwords import hash_password, verify_password
from bizora.auth.tokens import (
    Hs256TokenVerifier,
    TokenAuthError,
    mint_hs256_token,
    verify_hs256_token,
)
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app

TEST_SECRET = "TEST-ONLY-AUTH-SECRET"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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


def register(
    client: TestClient,
    email: str = "me@example.com",
    password: str = "correct-horse-9",
    name: str = "Me",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_a_verifiable_token(client: TestClient) -> None:
    body = register(client)

    assert body["user"]["email"] == "me@example.com"
    assert body["user"]["name"] == "Me"
    principal = verify_hs256_token(body["token"], TEST_SECRET)
    assert principal.user_id == body["user"]["user_id"]

    me = client.get("/api/v1/auth/me", headers=auth_headers(body["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "me@example.com"


def test_register_conflicts_on_duplicate_email(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ME@example.com", "password": "another-horse-9", "name": "Dup"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_register_rejects_bad_email_and_short_password(client: TestClient) -> None:
    bad_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "correct-horse-9"},
    )
    assert bad_email.status_code == 422

    short_password = client.post(
        "/api/v1/auth/register",
        json={"email": "you@example.com", "password": "short"},
    )
    assert short_password.status_code == 422


def test_login_round_trip_and_failures(client: TestClient) -> None:
    register(client)

    ok = client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "correct-horse-9"},
    )
    assert ok.status_code == 200
    assert verify_hs256_token(ok.json()["token"], TEST_SECRET).user_id

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "me@example.com", "password": "wrong-horse-9"},
    )
    assert wrong.status_code == 401

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "correct-horse-9"},
    )
    assert unknown.status_code == 401


def test_me_requires_a_valid_token(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401

    forged = client.get("/api/v1/auth/me", headers=auth_headers("forged.token.here"))
    assert forged.status_code == 401


def test_library_save_list_and_resave(client: TestClient) -> None:
    token = register(client)["token"]
    headers = auth_headers(token)

    assert client.get("/api/v1/users/me/papers", headers=headers).json() == []

    saved = client.post(
        "/api/v1/users/me/papers",
        headers=headers,
        json={
            "project_id": "project-papers",
            "graph_id": "graph-papers",
            "source_id": "paper-papers",
            "title": "AlphaFold paper",
        },
    )
    assert saved.status_code == 201

    resaved = client.post(
        "/api/v1/users/me/papers",
        headers=headers,
        json={
            "project_id": "project-papers",
            "graph_id": "graph-papers",
            "source_id": "paper-papers",
            "title": "AlphaFold paper (revised)",
        },
    )
    assert resaved.status_code == 200

    listed = client.get("/api/v1/users/me/papers", headers=headers)
    assert listed.status_code == 200
    assert [paper["title"] for paper in listed.json()] == ["AlphaFold paper (revised)"]


def test_library_rejects_bad_source_id(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.post(
        "/api/v1/users/me/papers",
        headers=auth_headers(token),
        json={
            "project_id": "project-papers",
            "graph_id": "graph-papers",
            "source_id": "not a source id!",
            "title": "Bad",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_notes_crud_and_cross_user_isolation(client: TestClient) -> None:
    mine = auth_headers(register(client)["token"])
    theirs = auth_headers(register(client, email="you@example.com")["token"])

    created = client.post(
        "/api/v1/papers/paper-papers/notes",
        headers=mine,
        json={"body": "Reproduce the tilt test first."},
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    assert [note["body"] for note in client.get("/api/v1/papers/paper-papers/notes", headers=mine).json()] == [
        "Reproduce the tilt test first."
    ]
    assert client.get("/api/v1/papers/paper-papers/notes", headers=theirs).json() == []

    updated = client.put(
        f"/api/v1/papers/paper-papers/notes/{note_id}",
        headers=mine,
        json={"body": "Reproduce the tilt test first, then BER."},
    )
    assert updated.status_code == 200
    assert updated.json()["body"] == "Reproduce the tilt test first, then BER."

    assert (
        client.put(
            f"/api/v1/papers/paper-papers/notes/{note_id}",
            headers=theirs,
            json={"body": "Hijacked."},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/papers/paper-papers/notes/{note_id}", headers=theirs).status_code == 404

    assert client.delete(f"/api/v1/papers/paper-papers/notes/{note_id}", headers=mine).status_code == 204
    assert client.get("/api/v1/papers/paper-papers/notes", headers=mine).json() == []


def test_notes_reject_blank_body_and_bad_paper(client: TestClient) -> None:
    headers = auth_headers(register(client)["token"])

    blank = client.post(
        "/api/v1/papers/paper-papers/notes", headers=headers, json={"body": "   "}
    )
    assert blank.status_code == 422

    bad_paper = client.post(
        "/api/v1/papers/not a paper!/notes", headers=headers, json={"body": "Hi."}
    )
    assert bad_paper.status_code == 404


def test_authenticated_extract_lands_in_the_library(client: TestClient) -> None:
    token = register(client)["token"]
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("paper.pdf", make_pdf_bytes("AlphaFold2 predicts structures."), "application/pdf")},
            data={
                "project_id": "project-papers",
                "graph_id": "graph-papers",
                "source_id": "paper-papers",
                "title": "AlphaFold paper",
            },
            headers=auth_headers(token),
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    listed = client.get("/api/v1/users/me/papers", headers=auth_headers(token)).json()
    assert [(paper["project_id"], paper["title"]) for paper in listed] == [
        ("project-papers", "AlphaFold paper")
    ]


def test_minted_tokens_verify_and_tampering_fails() -> None:
    token, expires_at = mint_hs256_token("user-1", TEST_SECRET)
    principal = verify_hs256_token(token, TEST_SECRET)
    assert principal.user_id == "user-1"
    assert principal.token_id
    assert principal.expires_at == expires_at.replace(microsecond=0)

    header, payload, _signature = token.split(".")
    with pytest.raises(TokenAuthError):
        verify_hs256_token(f"{header}.{payload}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", TEST_SECRET)

    old, _ = mint_hs256_token("user-1", TEST_SECRET, expires_in=timedelta(seconds=-60))
    with pytest.raises(TokenAuthError):
        verify_hs256_token(old, TEST_SECRET)


def test_password_hashing_round_trip_and_malformed() -> None:
    stored = hash_password("correct-horse-9")
    assert verify_password("correct-horse-9", stored) is True
    assert verify_password("wrong-horse-9", stored) is False
    assert verify_password("correct-horse-9", "not-a-hash") is False
    assert verify_password("correct-horse-9", "md5$1$xx$yy") is False
