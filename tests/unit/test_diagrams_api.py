"""Contract tests for the paper-diagrams endpoint (stub diagram provider)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_diagram_extraction import (
    ScriptedDiagramProvider,
    make_circuit_payload,
    make_methodology_payload,
    make_structure_payload,
)
from tests.unit.test_figure_ingest import make_fake_pdf_with_images
from tests.unit.test_figure_service import StubVisionProvider

from bizora.api import get_diagram_provider, get_muse_provider
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "domains"


@pytest.fixture
def stub_diagrams() -> ScriptedDiagramProvider:
    return ScriptedDiagramProvider()


@pytest.fixture
def client(
    stub_diagrams: ScriptedDiagramProvider, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("BIZORA_CACHE_DIR", str(tmp_path))
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
    app.dependency_overrides[get_muse_provider] = StubVisionProvider
    app.dependency_overrides[get_diagram_provider] = lambda: stub_diagrams

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_muse_provider, None)
        app.dependency_overrides.pop(get_diagram_provider, None)
        engine.dispose()


def seed_paper_with_figures(client: TestClient, source_id: str) -> list[str]:
    payload = json.loads((FIXTURES / "sram.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    create = client.post("/api/v1/graphs", json=payload)
    assert create.status_code == 201

    ingest = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/figures",
        files={
            "file": (
                "paper.pdf",
                make_fake_pdf_with_images(2, text="See Figure 1 and Figure 2."),
                "application/pdf",
            )
        },
        data={"source_id": source_id},
    )
    assert ingest.status_code == 201
    listed = client.get("/api/v1/graphs/fixture-sram/main/figures")
    assert listed.status_code == 200
    return [figure["figure_id"] for figure in listed.json()]


def test_diagrams_response_contract(
    client: TestClient, stub_diagrams: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-1")
    assert len(figure_ids) == 2
    for figure_id in figure_ids:
        stub_diagrams.figure_payloads[(figure_id, "circuit")] = make_circuit_payload()
    stub_diagrams.text_payloads["methodology"] = make_methodology_payload()
    stub_diagrams.text_payloads["structure"] = make_structure_payload()

    response = client.get("/api/v1/papers/paper-1/diagrams")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"methodology", "circuits", "structure", "validation", "sources"}
    assert len(body["circuits"]) == 2
    circuit = body["circuits"][0]
    assert circuit["version"] == 1
    assert circuit["components"][0]["type"] == "nmos"
    # No flow/structure figure exists, so methodology and structure
    # fall back to the persisted paper text.
    assert body["methodology"]["title"] == "flow"
    assert body["structure"]["title"] == "macro"
    # Aliased JSON keys must serialize with their spec names.
    assert body["circuits"][0]["nets"][0]["global"] is True
    assert set(body["validation"]) == {
        *(f"circuit:{fid}" for fid in figure_ids),
        "methodology",
        "structure",
    }
    report = body["validation"][f"circuit:{figure_ids[0]}"]
    assert set(report) == {"errors", "warnings", "stats"}
    assert report["errors"] == []
    assert report["stats"]["components"] == 2
    assert body["sources"] == {
        **{f"circuit:{fid}": f"figure:{fid}" for fid in figure_ids},
        "methodology": "text",
        "structure": "text",
    }


def test_diagrams_bare_path_alias(
    client: TestClient, stub_diagrams: ScriptedDiagramProvider
) -> None:
    figure_ids = seed_paper_with_figures(client, "paper-1")
    for figure_id in figure_ids:
        stub_diagrams.figure_payloads[(figure_id, "circuit")] = make_circuit_payload()
    stub_diagrams.text_payloads["methodology"] = make_methodology_payload()
    stub_diagrams.text_payloads["structure"] = make_structure_payload()

    response = client.get("/papers/paper-1/diagrams")

    assert response.status_code == 200
    assert len(response.json()["circuits"]) == 2


def test_diagrams_unknown_paper_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/papers/unknown-paper/diagrams").status_code == 404
    assert client.get("/api/v1/papers/bad!id/diagrams").status_code == 404


def test_diagrams_provider_failure_is_502(
    client: TestClient, stub_diagrams: ScriptedDiagramProvider
) -> None:
    seed_paper_with_figures(client, "paper-1")
    stub_diagrams.fail_extract = True

    response = client.get("/api/v1/papers/paper-1/diagrams")

    assert response.status_code == 502


def seed_text_only_paper(client: TestClient, source_id: str) -> None:
    payload = json.loads((FIXTURES / "sram.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    create = client.post("/api/v1/graphs", json=payload)
    assert create.status_code == 201

    ingest = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/figures",
        files={
            "file": (
                "paper.pdf",
                make_fake_pdf_with_images(0, text="Load data. Train model."),
                "application/pdf",
            )
        },
        data={"source_id": source_id},
    )
    assert ingest.status_code == 201


def test_diagrams_text_only_paper_serves_text_fallback(
    client: TestClient, stub_diagrams: ScriptedDiagramProvider
) -> None:
    seed_text_only_paper(client, "paper-text")
    stub_diagrams.text_payloads["methodology"] = make_methodology_payload()
    stub_diagrams.text_payloads["structure"] = make_structure_payload()

    response = client.get("/api/v1/papers/paper-text/diagrams")

    assert response.status_code == 200
    body = response.json()
    assert body["circuits"] == []
    assert body["methodology"]["title"] == "flow"
    assert body["structure"]["title"] == "macro"
    assert body["sources"] == {"methodology": "text", "structure": "text"}
    # The stub saw the persisted paper text, not an empty string.
    assert stub_diagrams.calls.get("text:methodology") == 1
    assert stub_diagrams.calls.get("text:structure") == 1
