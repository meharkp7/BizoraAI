"""Tests for the telemetry FastAPI router (standalone, no app edits)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bizora.contracts.run import ExperimentRun, RunState
from bizora.contracts.streaming import TelemetryEvent
from bizora.streaming.bus import TelemetryBus
from bizora.streaming.events import (
    make_metric_event,
    make_state_event,
    make_step_event,
)
from bizora.streaming.router import create_streaming_router
from bizora.streaming.sse import parse_event_frame


def make_client(bus: TelemetryBus, known_runs: set[str] | None = None) -> TestClient:
    """Build a test client serving only the streaming router."""
    from bizora.streaming.router import RunLoader

    loader: RunLoader | None = None
    if known_runs is not None:

        def present(run_id: str) -> ExperimentRun | None:
            if run_id not in known_runs:
                return None
            raise AssertionError("known-run bodies are covered loader-less")

        loader = present
    app = FastAPI()
    app.include_router(create_streaming_router(bus, get_run=loader, heartbeat_seconds=0.05))
    return TestClient(app)


def test_json_replay_lists_buffered_events() -> None:
    """The events endpoint returns buffered telemetry as JSON."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_metric_event("run-1", 1, "m-1", "loss", 0.5))
    client = make_client(bus)
    response = client.get("/api/v1/experiments/runs/run-1/telemetry/events")
    assert response.status_code == 200
    payload = response.json()
    assert [entry["seq"] for entry in payload] == [0, 1]
    assert TelemetryEvent.model_validate(payload[0]).run_id == "run-1"


def test_json_replay_supports_from_seq() -> None:
    """Replay cursors skip already-seen events."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_step_event("run-1", 1, 1))
    client = make_client(bus)
    response = client.get(
        "/api/v1/experiments/runs/run-1/telemetry/events",
        params={"from_seq": 1},
    )
    assert response.status_code == 200
    assert [entry["seq"] for entry in response.json()] == [1]


def test_stream_serves_sse_frames_then_ends() -> None:
    """A finished run streams its frames and then closes (R8)."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0, label="train"))
    bus.publish(make_state_event("run-1", 1, RunState.SUCCEEDED))
    client = make_client(bus)
    response = client.get("/api/v1/experiments/runs/run-1/telemetry/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in response.text.split("\n\n") if frame and not frame.startswith(":")]
    assert len(frames) == 2
    first_id, first_name, first_data = parse_event_frame(frames[0])
    assert (first_id, first_name) == (0, "step")
    assert first_data["step"]["label"] == "train"
    second_id, second_name, _ = parse_event_frame(frames[1])
    assert (second_id, second_name) == (1, "state")


def test_stream_resumes_from_cursor() -> None:
    """Reconnecting browsers resume without duplicates."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_step_event("run-1", 1, 1))
    bus.close_run("run-1")
    client = make_client(bus)
    response = client.get(
        "/api/v1/experiments/runs/run-1/telemetry/stream",
        params={"from_seq": 1},
    )
    assert response.status_code == 200
    frames = [frame for frame in response.text.split("\n\n") if frame and not frame.startswith(":")]
    assert len(frames) == 1
    event_id, _, _ = parse_event_frame(frames[0])
    assert event_id == 1


def test_unknown_run_returns_bizora_404() -> None:
    """The injected loader gates unknown runs with a 404."""
    bus = TelemetryBus()
    client = make_client(bus, known_runs={"run-1"})
    stream = client.get("/api/v1/experiments/runs/run-x/telemetry/stream")
    assert stream.status_code == 404
    assert stream.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    replay = client.get("/api/v1/experiments/runs/run-x/telemetry/events")
    assert replay.status_code == 404
