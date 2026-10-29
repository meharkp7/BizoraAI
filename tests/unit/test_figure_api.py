"""API tests for the paper-figure overlay endpoints."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from tests.unit.test_figure_ingest import make_fake_pdf_with_images
from tests.unit.test_figure_service import StubVisionProvider

from bizora.api import get_muse_provider
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "domains"


@pytest.fixture
def client() -> Iterator[TestClient]:
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

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_muse_provider, None)
        engine.dispose()


def seed_graph(client: TestClient) -> None:
    payload = json.loads((FIXTURES / "sram.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    create = client.post("/api/v1/graphs", json=payload)
    assert create.status_code == 201


def test_figure_ingest_lists_and_serves_images(client: TestClient) -> None:
    seed_graph(client)
    pdf = make_fake_pdf_with_images(1, text="See Figure 1.")

    ingest = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/figures",
        files={"file": ("paper.pdf", pdf, "application/pdf")},
    )
    assert ingest.status_code == 201
    body = ingest.json()
    assert len(body["figures"]) == 1
    assert body["figures"][0]["label"] == "Figure 1"
    # The stub links every region to "bitcell", which the sram fixture
    # graph does not have, so the merge keeps regions but unlinks them.
    assert body["figures"][0]["regions"][0]["node_id"] is None
    assert len(body["warnings"]) == 1

    listed = client.get("/api/v1/graphs/fixture-sram/main/figures")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    figure_id = body["figures"][0]["figure_id"]
    image = client.get(f"/api/v1/graphs/fixture-sram/main/figures/{figure_id}/image")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert len(image.content) > 0


def test_figure_endpoints_report_unknown_references(client: TestClient) -> None:
    seed_graph(client)
    missing_revision = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/9/figures",
        files={
            "file": ("paper.pdf", make_fake_pdf_with_images(1), "application/pdf")
        },
    )
    assert missing_revision.status_code == 404

    missing_image = client.get("/api/v1/graphs/fixture-sram/main/figures/nope/image")
    assert missing_image.status_code == 404

    empty_list = client.get("/api/v1/graphs/unknown/main/figures")
    assert empty_list.status_code == 200
    assert empty_list.json() == []
