"""Tests for project memory CRUD and copilot memory commands."""

import asyncio
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from tests.unit.test_entities_api import client, load_fixture_payload  # noqa: F401

__all__ = ["client"]

from bizora import api
from bizora.copilot.service import answer_with_llm
from bizora.copilot.testing import make_eval_context
from bizora.core.copilot_service import is_recall_command, parse_remember_command
from bizora.providers.copilot import (
    CopilotAssistantTurn,
    CopilotMessage,
    CopilotToolSpec,
)


def _seed(client: TestClient) -> None:
    assert (
        client.post("/api/v1/graphs", json=load_fixture_payload("sram")).status_code == 201
    )


def test_memory_crud_round_trip(client: TestClient) -> None:
    """Facts create, list newest-first, and delete."""
    created = client.post(
        "/api/v1/projects/project-1/memory",
        json={"fact": "The tapeout uses 65nm.", "created_by": "tester"},
    )
    assert created.status_code == 201
    fact_id = created.json()["id"]

    listed = client.get("/api/v1/projects/project-1/memory")
    assert [entry["fact"] for entry in listed.json()] == ["The tapeout uses 65nm."]

    assert (
        client.delete(f"/api/v1/projects/project-1/memory/{fact_id}").status_code == 204
    )
    assert client.get("/api/v1/projects/project-1/memory").json() == []
    assert (
        client.delete("/api/v1/projects/project-1/memory/9999").status_code == 404
    )


def test_memory_is_scoped_per_project(client: TestClient) -> None:
    """One project's facts never leak into another's listing."""
    client.post(
        "/api/v1/projects/project-1/memory",
        json={"fact": "Project one fact.", "created_by": "tester"},
    )

    assert client.get("/api/v1/projects/project-2/memory").json() == []


def test_remember_command_stores_and_recalls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'remember ...' persists; 'what do you remember' reads back."""
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)
    base = "/api/v1/graphs/fixture-sram/main/revisions/1/copilot"

    stored = client.post(base, json={"message": "remember the tapeout uses 65nm"})
    assert stored.status_code == 200
    assert "Noted" in stored.json()["reply"]

    listed = client.get("/api/v1/projects/fixture-sram/memory")
    assert [entry["fact"] for entry in listed.json()] == ["the tapeout uses 65nm"]

    recalled = client.post(base, json={"message": "what do you remember?"})
    assert recalled.status_code == 200
    assert "the tapeout uses 65nm" in recalled.json()["reply"]


def test_remember_command_streams_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Memory commands stream a status plus the confirmation."""
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)

    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/copilot/stream",
        json={"message": "remember to check the corners"},
    )

    assert response.status_code == 200
    assert "Updating project memory" in response.text
    assert "Noted" in response.text


def test_recall_with_empty_memory_explains(client: TestClient) -> None:
    """Empty memory says so instead of inventing facts."""
    _seed(client)

    response = client.post(
        "/api/v1/graphs/fixture-sram/main/revisions/1/copilot",
        json={"message": "what do you remember?"},
    )

    assert response.status_code == 200
    assert "don't remember anything" in response.json()["reply"]


def test_remember_parsing_rules() -> None:
    """Parsing strips wrappers and rejects bare 'remember'."""
    assert parse_remember_command("remember that X is true") == "X is true"
    assert parse_remember_command('remember "quoted fact"') == "quoted fact"
    assert parse_remember_command("remember") is None
    assert parse_remember_command("do you remember me?") is None
    assert is_recall_command("what do you remember about this?") is True
    assert is_recall_command("remember this please") is False


def test_orchestrator_sends_memory_to_provider() -> None:
    """Stored facts ride along with LLM turns as a context line."""

    class RecordingProvider:
        provider_name = "recording"

        def __init__(self) -> None:
            self.seen: list[list[CopilotMessage]] = []

        async def chat(
            self,
            messages: list[CopilotMessage],
            tools: list[CopilotToolSpec],  # noqa: ARG002 - recorded, not read
            *,
            response_schema: dict[str, object] | None = None,
        ) -> CopilotAssistantTurn:
            self.seen.append(list(messages))
            if response_schema is not None:
                return CopilotAssistantTurn(
                    content=json.dumps(
                        {
                            "reply": "65nm it is.",
                            "citations": [],
                            "proposal": None,
                            "assumed": False,
                        }
                    )
                )
            return CopilotAssistantTurn(content="No tools needed.")

    async def run_test() -> None:
        provider = RecordingProvider()
        context = replace(
            make_eval_context(), memory_facts=("the tapeout uses 65nm",)
        )

        await answer_with_llm("Which node?", context, provider)

        first_user = next(m for m in provider.seen[0] if m.role == "user")
        assert "[Memory: the tapeout uses 65nm]" in first_user.content

    asyncio.run(run_test())
