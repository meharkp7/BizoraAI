"""Tests for citation sources on cards and the paper text endpoint."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.unit.test_run_api import (  # noqa: F401
    client_with_db,
    make_graph_payload,
)

__all__ = ["client_with_db"]

from bizora.copilot.citations import CopilotAnswer, EvidenceCitation
from bizora.copilot.service import build_grounded_response
from bizora.copilot.testing import make_eval_context
from bizora.db.repository import save_paper_text


def test_evidence_card_carries_structured_source() -> None:
    """Evidence cards keep the machine-readable passage pointer."""
    response = build_grounded_response(
        CopilotAnswer(
            reply="The corner is 4 kHz.",
            citations=(
                EvidenceCitation(
                    source_id="paper-1",
                    page=3,
                    quote="the corner is 4 kHz",
                    target_id="filter",
                ),
            ),
            assumed=False,
        ),
        make_eval_context(),
    )

    assert len(response.cards) == 1
    source = response.cards[0].source
    assert source is not None
    assert source.source_id == "paper-1"
    assert source.page == 3
    assert source.quote == "the corner is 4 kHz"


def test_paper_text_endpoint_returns_markers_and_text(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """The text endpoint serves one paper's marked-up extraction."""
    client, session_factory = client_with_db
    created = client.post("/api/v1/graphs", json=make_graph_payload())
    assert created.status_code == 201
    with session_factory() as session:
        save_paper_text(
            session,
            project_id="project-api",
            graph_id="graph-api",
            source_id="paper-1",
            created_by="api-test",
            text="[Page 1]\nIntro words.\n[Page 2]\nThe corner is 4 kHz.",
            page_count=2,
        )
        session.commit()

    response = client.get("/api/v1/papers/paper-1/text")

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == "paper-1"
    assert body["page_count"] == 2
    assert "[Page 2]" in body["text"]
    assert len(body["sha256"]) == 64


def test_paper_text_endpoint_reports_unknown_source(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """Unknown sources report 404 with the standard error shape."""
    client, _ = client_with_db

    response = client.get("/api/v1/papers/no-such-paper/text")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
