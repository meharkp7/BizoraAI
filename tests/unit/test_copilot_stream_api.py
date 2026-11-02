"""API tests for the streaming copilot endpoint (SSE frames)."""

import json
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.unit.test_run_api import (  # noqa: F401
    client_with_db,
    make_graph_payload,
)

__all__ = ["client_with_db"]

from bizora import api
from bizora.providers.copilot import CopilotAssistantTurn, CopilotUsage
from bizora.providers.fixture_copilot import (
    RecordedTranscript,
    ScriptedCopilotProvider,
)


def _seed(client: TestClient) -> None:
    created = client.post("/api/v1/graphs", json=make_graph_payload())
    assert created.status_code == 201


def _frames(body: str) -> list[tuple[str, dict[str, object]]]:
    parsed: list[tuple[str, dict[str, object]]] = []
    for chunk in body.split("\n\n"):
        if not chunk.strip():
            continue
        kind = payload = None
        for line in chunk.splitlines():
            if line.startswith("event: "):
                kind = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        assert kind is not None and payload is not None
        parsed.append((kind, payload))
    return parsed


def test_stream_endpoint_frames_status_then_done(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fast path streams one status before the final response."""
    client, _ = client_with_db
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions/1/copilot/stream",
        json={"message": "hello"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert [kind for kind, _ in frames] == ["status", "done"]
    assert frames[0][1]["message"] == "Answering from the workspace graph…"
    done_payload = frames[1][1]
    assert isinstance(done_payload["response"], dict)
    assert done_payload["response"]["reply"]  # type: ignore[index]


def test_stream_endpoint_streams_llm_rounds_and_records_usage(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An LLM turn streams per-round progress and records usage once done."""
    client, _ = client_with_db
    _seed(client)
    transcript = RecordedTranscript(
        turns=(
            CopilotAssistantTurn(
                content="Thinking done.",
                usage=CopilotUsage(
                    input_tokens=10, output_tokens=4, model="scripted-test"
                ),
            ),
            CopilotAssistantTurn(
                content=json.dumps(
                    {
                        "reply": "Streamed answer.",
                        "citations": [],
                        "proposal": None,
                        "assumed": True,
                    }
                ),
                usage=CopilotUsage(
                    input_tokens=20, output_tokens=6, model="scripted-test"
                ),
            ),
        )
    )
    provider = ScriptedCopilotProvider(transcript)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: provider)

    response = client.post(
        "/api/v1/graphs/project-api/graph-api/revisions/1/copilot/stream",
        json={"message": "why is this so slow?"},
    )

    assert response.status_code == 200
    frames = _frames(response.text)
    assert [kind for kind, _ in frames] == ["status", "status", "done"]
    assert frames[0][1]["message"] == "Thinking (round 1)…"
    assert frames[1][1]["message"] == "Writing the final answer…"
    assert provider.exhausted

    summary = client.get("/api/v1/usage/summary?days=1")
    assert summary.json()["totals"]["calls"] == 1
