"""R8 acceptance probes: live delivery latency and stream shutdown.

- Telemetry published by the worker must be observable by a subscriber
  within 2 seconds (R8 latency bar; in-process delivery is far below).
- Publishing a terminal state, or stopping (closing) the run, must end
  the stream so the browser stops waiting.
"""

import time

from bizora.contracts.run import RunState
from bizora.contracts.streaming import TelemetryLogLevel
from bizora.streaming.bus import TelemetryBus
from bizora.streaming.events import (
    make_log_event,
    make_metric_event,
    make_pack_signal_event,
    make_state_event,
    make_step_event,
)

LATENCY_BUDGET_SECONDS = 2.0


def test_published_telemetry_arrives_within_two_seconds() -> None:
    """Every event kind is pollable well inside the R8 latency bar."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:
        builders = [
            lambda seq: make_step_event("run-1", seq, seq),
            lambda seq: make_metric_event("run-1", seq, f"m-{seq}", "loss", 0.1),
            lambda seq: make_log_event("run-1", seq, TelemetryLogLevel.INFO, f"line {seq}"),
            lambda seq: make_pack_signal_event("run-1", seq, "sig", "Signal", [float(seq)]),
        ]
        worst = 0.0
        for index, build in enumerate(builders):
            bus.publish(build(index))
            started = time.monotonic()
            event = subscription.poll(timeout_seconds=LATENCY_BUDGET_SECONDS)
            elapsed = time.monotonic() - started
            assert event is not None
            worst = max(worst, elapsed)
        assert worst < LATENCY_BUDGET_SECONDS
    finally:
        subscription.close()


def test_terminal_state_stops_the_stream() -> None:
    """A terminal lifecycle event ends polling promptly."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:
        bus.publish(make_step_event("run-1", 0, 0))
        bus.publish(make_state_event("run-1", 1, RunState.SUCCEEDED))
        started = time.monotonic()
        seen = 0
        while not subscription.done:
            event = subscription.poll(timeout_seconds=LATENCY_BUDGET_SECONDS)
            if event is not None:
                seen += 1
        assert seen == 2
        assert time.monotonic() - started < LATENCY_BUDGET_SECONDS
    finally:
        subscription.close()


def test_stopping_a_run_stops_the_stream() -> None:
    """Closing (stopping) a run unblocks subscribers immediately."""
    bus = TelemetryBus()
    subscription = bus.subscribe("run-1")
    try:
        bus.close_run("run-1")
        started = time.monotonic()
        assert subscription.poll(timeout_seconds=LATENCY_BUDGET_SECONDS) is None
        assert subscription.done
        assert time.monotonic() - started < LATENCY_BUDGET_SECONDS
    finally:
        subscription.close()
