"""Tests for SSE encoding of telemetry events."""

import pytest

from bizora.contracts.streaming import TelemetryEvent
from bizora.streaming.events import make_metric_event, make_step_event
from bizora.streaming.sse import (
    SSE_CONTENT_TYPE,
    format_event,
    format_heartbeat,
    parse_event_frame,
)


def test_content_type_is_event_stream() -> None:
    """The stream must use the SSE media type."""
    assert SSE_CONTENT_TYPE == "text/event-stream"


def test_frame_carries_id_event_and_data() -> None:
    """Frames expose seq as id, kind as event, and JSON as data."""
    frame = format_event(make_metric_event("run-1", 7, "m-1", "loss", 0.5, unit="nats"))
    assert frame.startswith("id: 7\nevent: metric\ndata: ")
    assert frame.endswith("\n\n")
    event_id, event_name, data = parse_event_frame(frame)
    assert event_id == 7
    assert event_name == "metric"
    assert data["run_id"] == "run-1"
    assert data["metric"]["value"] == 0.5


def test_frame_round_trips_through_contract() -> None:
    """Parsed frame data re-validates as the original event."""
    original = make_step_event("run-1", 3, 1, label="train", total_steps=4)
    _, _, data = parse_event_frame(format_event(original))
    assert TelemetryEvent.model_validate(data) == original


def test_heartbeat_is_a_comment_frame() -> None:
    """Heartbeats are SSE comments browsers ignore."""
    assert format_heartbeat() == ": heartbeat\n\n"


def test_parse_rejects_malformed_frames() -> None:
    """Missing fields and non-object data fail loudly."""
    with pytest.raises(ValueError):
        parse_event_frame("event: metric\n\n")
    with pytest.raises(ValueError):
        parse_event_frame("id: 1\nevent: metric\ndata: [1, 2]\n\n")
    with pytest.raises(ValueError):
        parse_event_frame("bogus line\n\n")
