"""Tests for the telemetry broadcast bus."""

import threading

import pytest

from bizora.contracts.run import RunState
from bizora.contracts.streaming import TelemetryLogLevel
from bizora.streaming.bus import TelemetryBus
from bizora.streaming.events import (
    make_log_event,
    make_metric_event,
    make_state_event,
    make_step_event,
)


def test_publish_replay_round_trip() -> None:
    """Buffered events replay from any cursor."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_metric_event("run-1", 1, "m-1", "loss", 0.5))
    replayed = bus.replay("run-1")
    assert [event.seq for event in replayed] == [0, 1]
    assert [event.seq for event in bus.replay("run-1", from_seq=1)] == [1]
    assert bus.replay("run-unknown") == ()


def test_subscribe_replays_then_tails_live() -> None:
    """Subscribers see history first, then live publications."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    subscription = bus.subscribe("run-1")
    try:
        first = subscription.poll(0.1)
        assert first is not None and first.seq == 0
        bus.publish(make_log_event("run-1", 1, TelemetryLogLevel.INFO, "hi"))
        second = subscription.poll(2.0)
        assert second is not None and second.seq == 1
        assert not subscription.done
    finally:
        subscription.close()


def test_terminal_state_event_ends_stream() -> None:
    """A terminal lifecycle event closes the run and ends polling."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:
        bus.publish(make_step_event("run-1", 0, 0))
        bus.publish(make_state_event("run-1", 1, RunState.SUCCEEDED))
        assert bus.is_closed("run-1")
        assert subscription.poll(2.0) is not None
        terminal = subscription.poll(2.0)
        assert terminal is not None and terminal.state is not None
        assert subscription.poll(0.1) is None
        assert subscription.done
    finally:
        subscription.close()


def test_close_run_stops_waiting_subscribers() -> None:
    """Stopping a run ends its stream (R8 acceptance)."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:
        bus.close_run("run-1")
        assert subscription.poll(2.0) is None
        assert subscription.done
    finally:
        subscription.close()


def test_closed_run_serves_replay_only() -> None:
    """Late subscribers to a finished run drain the buffer, then end."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_state_event("run-1", 1, RunState.FAILED, error="boom"))
    subscription = bus.subscribe("run-1")
    try:
        assert subscription.poll(0.1) is not None
        assert subscription.poll(0.1) is not None
        assert subscription.poll(0.1) is None
        assert subscription.done
    finally:
        subscription.close()


def test_publish_after_close_is_rejected() -> None:
    """Closed streams refuse further events."""
    bus = TelemetryBus()
    bus.close_run("run-1")
    with pytest.raises(ValueError, match="closed"):
        bus.publish(make_step_event("run-1", 0, 0))


def test_sequence_must_increase_strictly() -> None:
    """Out-of-order or duplicate seq values are rejected."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-1", 5, 0))
    with pytest.raises(ValueError, match="must exceed"):
        bus.publish(make_step_event("run-1", 5, 1))
    with pytest.raises(ValueError, match="must exceed"):
        bus.publish(make_step_event("run-1", 3, 1))
    assert bus.next_seq("run-1") == 6


def test_runs_are_isolated() -> None:
    """Events and cursors never leak across runs."""
    bus = TelemetryBus()
    bus.publish(make_step_event("run-a", 0, 0))
    bus.publish(make_step_event("run-b", 0, 0))
    assert len(bus.replay("run-a")) == 1
    assert len(bus.replay("run-b")) == 1
    bus.close_run("run-a")
    assert bus.is_closed("run-a")
    assert not bus.is_closed("run-b")


def test_fan_out_reaches_all_subscribers() -> None:
    """Every live subscriber receives every published event."""
    bus = TelemetryBus()
    first = bus.subscribe("run-1")
    second = bus.subscribe("run-1")
    try:
        bus.publish(make_metric_event("run-1", 0, "m-1", "loss", 0.25))
        assert first.poll(2.0) is not None
        assert second.poll(2.0) is not None
    finally:
        first.close()
        second.close()


def test_publish_from_worker_thread_reaches_subscriber() -> None:
    """The execution worker thread can publish while SSE polls."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:

        def worker() -> None:
            seq = bus.next_seq("run-1")
            bus.publish(make_step_event("run-1", seq, 0))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
        assert subscription.poll(2.0) is not None
    finally:
        subscription.close()


def test_buffer_bound_is_enforced() -> None:
    """Publishing past the buffer cap fails instead of growing memory."""
    bus = TelemetryBus(max_buffered_per_run=2)
    bus.publish(make_step_event("run-1", 0, 0))
    bus.publish(make_step_event("run-1", 1, 1))
    with pytest.raises(ValueError, match="exceeded"):
        bus.publish(make_step_event("run-1", 2, 2))
