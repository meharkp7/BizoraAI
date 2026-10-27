"""API tests for paper upload and results-table listing."""

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from bizora.api import get_baseten_provider
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.table import ExtractedTable
from bizora.db.base import Base
from bizora.db.session import get_db_session
from bizora.main import app
from bizora.providers.base import (
    MethodologyExtractionRequest,
    MethodologyExtractionResult,
)
from bizora.providers.baseten import BasetenProviderError
from bizora.providers.tables import (
    TableExtractionRequest,
    TableExtractionResult,
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


def make_pdf_bytes(text: str) -> bytes:
    """Assemble a minimal one-page PDF with computed xref offsets."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode("latin-1")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return out


def make_graph_payload() -> dict[str, object]:
    """Build a minimal graph payload for the fake provider."""
    return {
        "project_id": "project-papers",
        "graph_id": "graph-papers",
        "version": 1,
        "parent_version": None,
        "title": "Uploaded methodology",
        "source_ids": ["paper-papers"],
        "nodes": [
            {"id": "input", "kind": "input", "label": "Image"},
            {"id": "output", "kind": "output", "label": "Predictions"},
        ],
        "edges": [
            {"id": "edge-1", "source": "input", "target": "output"},
        ],
        "created_by": "papers-test",
    }


def make_table() -> ExtractedTable:
    return ExtractedTable(
        table_id="table-1",
        project_id="project-papers",
        graph_id="graph-papers",
        source_id="paper-papers",
        caption="CASP14 results.",
        columns=("Method", "TM-score"),
        rows=(("AlphaFold2", "0.92"),),
        created_by="papers-test",
    )


class FakePaperProvider:
    """Fake provider implementing both extraction methods."""

    def __init__(
        self,
        *,
        fail_graph: bool = False,
        fail_tables: bool = False,
    ) -> None:
        self.fail_graph = fail_graph
        self.fail_tables = fail_tables

    async def extract_methodology(
        self, request: MethodologyExtractionRequest
    ) -> MethodologyExtractionResult:
        if self.fail_graph:
            raise BasetenProviderError("Graph extraction failed.")
        graph_data = dict(make_graph_payload())
        graph_data["project_id"] = request.project_id
        graph_data["graph_id"] = request.graph_id
        graph_data["created_by"] = request.created_by
        graph_data["source_ids"] = [request.source_id]
        graph_data["title"] = request.title or graph_data["title"]
        return MethodologyExtractionResult(
            draft_graph=MethodologyGraph.model_validate(graph_data),
            provider_name="fake",
            model_name="test-model",
        )

    async def extract_tables(
        self, request: TableExtractionRequest
    ) -> TableExtractionResult:
        if self.fail_tables:
            raise BasetenProviderError("Table extraction failed.")
        table = make_table().model_copy(
            update={
                "project_id": request.project_id,
                "graph_id": request.graph_id,
                "source_id": request.source_id,
                "created_by": request.created_by,
            }
        )
        return TableExtractionResult(
            draft_tables=(table,),
            provider_name="fake",
            model_name="test-model",
        )


def upload(
    client: TestClient, content: bytes, filename: str = "paper.pdf"
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/v1/papers/extract",
        files={"file": (filename, content, "application/pdf")},
        data={
            "project_id": "project-papers",
            "graph_id": "graph-papers",
            "source_id": "paper-papers",
            "created_by": "papers-test",
            "title": "AlphaFold paper",
        },
    )
    return response


def test_upload_pdf_extracts_graph_and_tables(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = upload(client, make_pdf_bytes("AlphaFold2 predicts structures."))
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    body = response.json()
    assert body["graph"]["version"] == 1
    assert body["graph"]["title"] == "AlphaFold paper"
    assert [table["table_id"] for table in body["tables"]] == ["table-1"]
    assert body["tables"][0]["rows"] == [["AlphaFold2", "0.92"]]
    assert body["warnings"] == []
    assert body["page_count"] == 1
    assert body["truncated"] is False


def test_upload_rejects_non_pdf(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = upload(client, b"not a pdf", filename="paper.txt")
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_upload_graph_failure_returns_502(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider(
        fail_graph=True
    )
    try:
        response = upload(client, make_pdf_bytes("Some paper text."))
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 502


def test_provider_failure_is_logged_server_side(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider(
        fail_graph=True
    )
    try:
        with caplog.at_level("WARNING", logger="bizora.api"):
            response = upload(client, make_pdf_bytes("Some paper text."))
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 502
    assert "Graph extraction failed." in caplog.text


def test_table_failure_warns_but_returns_graph(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider(
        fail_tables=True
    )
    try:
        response = upload(client, make_pdf_bytes("Some paper text."))
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    body = response.json()
    assert body["graph"]["version"] == 1
    assert body["tables"] == []
    assert body["warnings"] == [
        "Results tables could not be extracted: the provider request failed."
    ]


def test_list_tables_returns_persisted_tables(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        upload(client, make_pdf_bytes("AlphaFold2 predicts structures."))
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    response = client.get("/api/v1/graphs/project-papers/graph-papers/tables")

    assert response.status_code == 200
    assert [table["table_id"] for table in response.json()] == ["table-1"]


def test_list_tables_unknown_graph_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/graphs/missing/graph/tables")

    assert response.status_code == 404


def test_parse_returns_metadata_without_provider(client: TestClient) -> None:
    response = client.post(
        "/api/v1/papers/parse",
        files={"file": ("study.pdf", make_pdf_bytes("Some paper body."), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "study.pdf"
    assert body["title"] is None
    assert body["authors"] == []
    assert body["page_count"] == 1
    assert body["chars"] > 0
    assert len(body["sha256"]) == 64
    assert body["suggested"]["project_id"].startswith("study-")
    assert body["suggested"]["source_id"].startswith("paper-")


def test_parse_rejects_non_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/v1/papers/parse",
        files={"file": ("paper.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_parse_returns_503_when_settings_invalid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bizora import api

    def broken_settings() -> object:
        raise ValueError("Baseten is enabled but its API key is missing.")

    monkeypatch.setattr(api, "get_settings", broken_settings)
    response = client.post(
        "/api/v1/papers/parse",
        files={
            "file": (
                "study.pdf",
                make_pdf_bytes("Some paper body."),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider configuration is invalid."


def test_extract_accepts_blank_fields_with_suggestions(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = client.post(
            "/api/v1/papers/extract",
            files={
                "file": (
                    "study.pdf",
                    make_pdf_bytes("AlphaFold2 predicts structures."),
                    "application/pdf",
                )
            },
            data={},
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 201
    body = response.json()
    assert body["graph"]["project_id"].startswith("study-")
    assert body["graph"]["graph_id"].startswith("study-graph-")
    assert body["graph"]["source_ids"] == [body["graph"]["source_ids"][0]]
    assert body["graph"]["source_ids"][0].startswith("paper-")
    assert body["graph"]["created_by"] == "paper-upload"


def test_extract_rejects_invalid_source_id(client: TestClient) -> None:
    app.dependency_overrides[get_baseten_provider] = lambda: FakePaperProvider()
    try:
        response = client.post(
            "/api/v1/papers/extract",
            files={
                "file": (
                    "study.pdf",
                    make_pdf_bytes("Some paper text."),
                    "application/pdf",
                )
            },
            data={"source_id": "has spaces"},
        )
    finally:
        app.dependency_overrides.pop(get_baseten_provider, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
