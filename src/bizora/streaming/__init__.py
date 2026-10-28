"""Live run-telemetry streaming (Phase 7, R8).

This package owns the server side of the experiment workspace's live
view: validated event builders, an in-memory per-run broadcast bus, SSE
encoding, honesty labelling, the measured-vs-paper-reported comparison
view, and a FastAPI router the application owner mounts (see
:mod:`bizora.streaming.router` for the wiring note).
"""

from bizora.streaming.bus import TelemetryBus, TelemetrySubscription
from bizora.streaming.sse import (
    SSE_CONTENT_TYPE,
    format_event,
    format_heartbeat,
)

__all__ = [
    "SSE_CONTENT_TYPE",
    "TelemetryBus",
    "TelemetrySubscription",
    "format_event",
    "format_heartbeat",
]
