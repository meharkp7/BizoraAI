
"""API tests using an isolated in-memory database."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.api import get_baseten_provider
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)
from bizora.providers.fireworks import (
    FireworksProviderError,
)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide a test client backed by an isolated SQLite database."""
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
        engine.dispose()


def make_graph_payload() -> dict[str, object]:
    """Build a minimal graph request payload."""
    return {
        "project_id": "project-api",
        "graph_id": "graph-api",
        "version": 1,
        "parent_version": None,
        "title": "Vision Transformer",
        "source_ids": ["paper-api"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "encoder", "kind": "model", "label": "Encoder"},
            {"id": "output", "kind": "output", "label": "Predictions"},
        ],
        "edges": [
            {"id": "edge-1", "source": "input", "target": "encoder"},
            {"id": "edge-2", "source": "encoder", "target": "output"},
        ],
        "created_by": "api-test",
    }


class FakeMethodologyProvider:
    """Fake provider for extraction endpoint tests."""

    def __init__(self, graph_payload: dict[str, object]) -> None:
        self.graph_payload = graph_payload

    async def extract_methodology(
        self,
        request: MethodologyExtractionRequest,
    ) -> MethodologyExtractionResult:
        from bizora.contracts.graph import MethodologyGraph

        graph_data = dict(self.graph_payload)
        graph_data["project_id"] = request.project_id
        graph_data["graph_id"] = request.graph_id
        graph_data["version"] = 1
        graph_data["parent_version"] = None
        graph_data["created_by"] = request.created_by
        graph_data["source_ids"] = [request.source_id]
        graph_data["title"] = request.title or graph_data["title"]

        return MethodologyExtractionResult(
            draft_graph=MethodologyGraph.model_validate(graph_data),
            provider_name="fake",
            model_name="test-model",
        )

def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_retrieve_graph(client: TestClient) -> None:
    payload = make_graph_payload()

    created = client.post("/api/v1/graphs", json=payload)

    assert created.status_code == 201
    assert created.json()["graph_id"] == "graph-api"
    assert created.json()["version"] == 1

    retrieved = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/1"
    )

    assert retrieved.status_code == 200
    assert retrieved.json() == created.json()


def test_duplicate_initial_graph_returns_conflict(
    client: TestClient,
) -> None:
    payload = make_graph_payload()

    first = client.post("/api/v1/graphs", json=payload)
    duplicate = client.post("/api/v1/graphs", json=payload)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "error" in duplicate.json()


def test_missing_revision_returns_404(client: TestClient) -> None:
    response = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/99"
    )

    assert response.status_code == 404


def test_invalid_graph_request_returns_422(client: TestClient) -> None:
    payload = make_graph_payload()
    payload["edges"] = [
        {"id": "edge-1", "source": "missing-node", "target": "encoder"}
    ]

    response = client.post("/api/v1/graphs", json=payload)

    assert response.status_code == 422


def test_create_graph_revision_increments_version(
    client: TestClient,
) -> None:
    payload = make_graph_payload()
    initial = client.post("/api/v1/graphs", json=payload)
    assert initial.status_code == 201

    revised = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions",
        json=initial.json(),
    )

    assert revised.status_code == 201
    assert revised.json()["version"] == 2
    assert revised.json()["parent_version"] == 1
    assert revised.json()["graph_id"] == "graph-api"

    retrieved = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/2"
    )
    assert retrieved.status_code == 200
    assert retrieved.json() == revised.json()


def test_create_graph_revision_rejects_stale_snapshot(
    client: TestClient,
) -> None:
    initial = client.post(
        "/api/v1/graphs",
        json=make_graph_payload(),
    )
    assert initial.status_code == 201

    stale_snapshot = initial.json()
    stale_snapshot["title"] = "Edited stale copy"

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions",
        json=stale_snapshot,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_create_graph_revision_requires_existing_graph(
    client: TestClient,
) -> None:
    payload = make_graph_payload()
    payload["project_id"] = "missing-project"

    response = client.post(
        "/api/v1/graphs/missing-project/graph-api/revisions",
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_create_graph_revision_rejects_mismatched_path(
    client: TestClient,
) -> None:
    payload = make_graph_payload()

    response = client.post(
        "/api/v1/graphs/another-project/graph-api/revisions",
        json=payload,
    )

    assert response.status_code == 422


def test_apply_graph_patch_creates_revision(client: TestClient) -> None:
    initial = client.post("/api/v1/graphs", json=make_graph_payload())
    assert initial.status_code == 201

    patch = {
        "patch_id": "patch-api-1",
        "base_graph_id": "graph-api",
        "base_version": 1,
        "operation": "add_node",
        "target_id": None,
        "payload": {
            "node": {
                "id": "normalizer",
                "kind": "preprocessing",
                "label": "Normalize image",
            }
        },
        "rationale": "Add image normalization",
        "requested_by": "api-test",
    }

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/patches",
        json=patch,
    )

    assert response.status_code == 201
    assert response.json()["version"] == 2
    assert response.json()["parent_version"] == 1
    assert any(
        node["id"] == "normalizer"
        for node in response.json()["nodes"]
    )


def test_apply_graph_patch_rejects_missing_base_revision(
    client: TestClient,
) -> None:
    patch = {
        "patch_id": "patch-api-missing",
        "base_graph_id": "graph-api",
        "base_version": 1,
        "operation": "add_node",
        "payload": {
            "node": {
                "id": "normalizer",
                "kind": "preprocessing",
                "label": "Normalize image",
            }
        },
        "rationale": "Test missing graph",
        "requested_by": "api-test",
    }

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/patches",
        json=patch,
    )

    assert response.status_code == 404


def test_apply_graph_patch_rejects_invalid_result(
    client: TestClient,
) -> None:
    initial = client.post("/api/v1/graphs", json=make_graph_payload())
    assert initial.status_code == 201

    patch = {
        "patch_id": "patch-api-invalid",
        "base_graph_id": "graph-api",
        "base_version": 1,
        "operation": "add_edge",
        "payload": {
            "edge": {
                "id": "bad-edge",
                "source": "input",
                "target": "missing-node",
            }
        },
        "rationale": "Test invalid edge",
        "requested_by": "api-test",
    }

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/patches",
        json=patch,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_GRAPH_PATCH"

    latest = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/1"
    )
    assert latest.status_code == 200
    assert latest.json()["version"] == 1

def test_extract_graph_persists_initial_revision(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: (
        FakeMethodologyProvider(make_graph_payload())
    )

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": (
                    "The paper describes an image encoder and prediction head."
                ),
                "project_id": "project-api",
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
                "title": "Extracted methodology",
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    assert response.json()["version"] == 1
    assert response.json()["parent_version"] is None
    assert response.json()["project_id"] == "project-api"
    assert response.json()["graph_id"] == "graph-api"

    retrieved = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/1"
    )
    assert retrieved.status_code == 200
    assert retrieved.json() == response.json()

def test_extract_graph_rejects_duplicate_initial_revision(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: (
        FakeMethodologyProvider(make_graph_payload())
    )

    payload = {
        "paper_text": "A research paper about image classification.",
        "project_id": "project-api",
        "graph_id": "graph-api",
        "source_id": "paper-api",
        "created_by": "api-test",
        "title": "Extracted methodology",
    }

    try:
        first = client.post("/api/v1/graphs/extract", json=payload)
        duplicate = client.post("/api/v1/graphs/extract", json=payload)
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"

def test_extract_graph_returns_502_on_provider_failure(
    client: TestClient,
) -> None:
    class FailingProvider:
        async def extract_methodology(
            self,
            request: MethodologyExtractionRequest,
        ) -> MethodologyExtractionResult:
            raise FireworksProviderError("simulated provider failure")

    app.dependency_overrides[get_baseten_provider] = FailingProvider

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": "Paper text",
                "project_id": "project-api",
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
                "title": "Test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 502
    assert "simulated provider failure" not in response.text


def test_extract_graph_returns_503_when_provider_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bizora import api
    from bizora.core.config import Settings

    monkeypatch.setattr(
        api,
        "get_settings",
        lambda: Settings(_env_file=None, BIZORA_ENABLE_BASETEN=False),
    )

    response = client.post(
        "/api/v1/graphs/extract",
        json={
            "paper_text": "Paper text",
            "project_id": "project-api",
            "graph_id": "graph-api",
            "source_id": "paper-api",
            "created_by": "api-test",
            "title": "Test",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Baseten provider is disabled."

def test_extract_graph_rejects_invalid_provider_graph(
    client: TestClient,
) -> None:
    payload = make_graph_payload()
    payload["edges"] = [
        {
            "id": "invalid-edge",
            "source": "input",
            "target": "missing-node",
        }
    ]

    app.dependency_overrides[get_baseten_provider] = lambda: (
        FakeMethodologyProvider(payload)
    )

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": "Paper text",
                "project_id": "project-api",
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
                "title": "Test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_GRAPH"

    retrieved = client.get(
        "/api/v1/graphs/project-api/graph-api/revisions/1"
    )
    assert retrieved.status_code == 404


def test_extract_rejects_overlong_title_without_calling_provider(
    client: TestClient,
) -> None:
    class ExplodingProvider:
        async def extract_methodology(
            self,
            request: MethodologyExtractionRequest,
        ) -> MethodologyExtractionResult:
            raise AssertionError("invalid request must not reach the provider")

    app.dependency_overrides[get_baseten_provider] = ExplodingProvider

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": "Paper text",
                "project_id": "project-api",
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
                "title": "T" * 301,
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422


def test_extract_rejects_overlong_project_id(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: (
        FakeMethodologyProvider(make_graph_payload())
    )

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": "Paper text",
                "project_id": "p" * 129,
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422


def test_extract_rejects_enormous_paper_text(
    client: TestClient,
) -> None:
    from bizora.providers.base import MAX_PAPER_TEXT_LENGTH

    app.dependency_overrides[get_baseten_provider] = lambda: (
        FakeMethodologyProvider(make_graph_payload())
    )

    try:
        response = client.post(
            "/api/v1/graphs/extract",
            json={
                "paper_text": "x" * (MAX_PAPER_TEXT_LENGTH + 1),
                "project_id": "project-api",
                "graph_id": "graph-api",
                "source_id": "paper-api",
                "created_by": "api-test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422