"""API tests for copilot conversation threads."""

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

THREADS = "/api/v1/graphs/project-api/graph-api/copilot/threads"


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


def _thread_paths(version: int = 1) -> tuple[str, str]:
    base = f"/api/v1/graphs/project-api/graph-api/revisions/{version}/copilot"
    return THREADS, base


def test_thread_lifecycle_create_list_get(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """Threads create empty, list newest-first, and read back with no turns."""
    client, _ = client_with_db
    _seed(client)
    threads, _ = _thread_paths()

    created = client.post(threads, json={"title": "First chat"})
    assert created.status_code == 201
    thread_id = created.json()["thread_id"]
    assert created.json()["title"] == "First chat"
    assert created.json()["turn_count"] == 0

    listed = client.get(threads)
    assert [entry["thread_id"] for entry in listed.json()] == [thread_id]

    fetched = client.get(f"{threads}/{thread_id}")
    assert fetched.status_code == 200
    assert fetched.json()["turns"] == []


def test_ask_once_records_turn_and_names_thread(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ask with thread_id stores the pair and titles from the message."""
    client, _ = client_with_db
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)
    threads, base = _thread_paths()

    thread_id = client.post(threads, json={}).json()["thread_id"]
    answer = client.post(
        base, json={"message": "hello there", "thread_id": thread_id}
    )
    assert answer.status_code == 200

    fetched = client.get(f"{threads}/{thread_id}").json()
    assert fetched["title"] == "hello there"
    assert [(turn["seq"], turn["role"]) for turn in fetched["turns"]] == [
        (0, "user"),
        (1, "assistant"),
    ]
    assert fetched["turns"][0]["message"] == "hello there"
    assert fetched["turns"][0]["response"] is None
    assert fetched["turns"][1]["response"]["reply"] == answer.json()["reply"]

    listed = client.get(threads).json()
    assert listed[0]["turn_count"] == 2


def test_stream_records_turn_after_done(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A streamed turn lands in the thread once the done frame arrives."""
    client, _ = client_with_db
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)
    threads, base = _thread_paths()

    thread_id = client.post(threads, json={"title": "Kept title"}).json()["thread_id"]
    response = client.post(
        f"{base}/stream", json={"message": "hello", "thread_id": thread_id}
    )
    assert response.status_code == 200
    assert [kind for kind, _ in _frames(response.text)][-1] == "done"

    fetched = client.get(f"{threads}/{thread_id}").json()
    assert fetched["title"] == "Kept title"
    assert len(fetched["turns"]) == 2


def test_unknown_thread_rejected_before_answering(
    client_with_db: tuple[TestClient, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ask and stream 404 unknown threads without spending a turn."""
    client, _ = client_with_db
    _seed(client)
    monkeypatch.setattr(api, "_copilot_provider_or_none", lambda: None)
    _, base = _thread_paths()

    answer = client.post(base, json={"message": "hi", "thread_id": "nope"})
    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    streamed = client.post(f"{base}/stream", json={"message": "hi", "thread_id": "nope"})
    assert streamed.status_code == 404
    assert streamed.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_threads_are_scoped_to_their_graph(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """A thread id from another graph reads as not found."""
    client, _ = client_with_db
    _seed(client)
    other = dict(make_graph_payload())
    other["graph_id"] = "graph-other"
    assert client.post("/api/v1/graphs", json=other).status_code == 201
    threads, _ = _thread_paths()

    thread_id = client.post(threads, json={}).json()["thread_id"]
    other_threads = "/api/v1/graphs/project-api/graph-other/copilot/threads"

    assert client.get(other_threads).json() == []
    missing = client.get(f"{other_threads}/{thread_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_threads_on_unknown_graph_are_not_found(
    client_with_db: tuple[TestClient, Callable[[], Session]],
) -> None:
    """Thread routes 404 when the graph was never persisted."""
    client, _ = client_with_db
    missing = "/api/v1/graphs/nope/nope/copilot/threads"

    assert client.post(missing, json={}).status_code == 404
    assert client.get(missing).status_code == 404
    assert client.get(f"{missing}/whatever").status_code == 404
