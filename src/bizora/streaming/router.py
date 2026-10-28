"""FastAPI router for live telemetry over SSE (Phase 7, R8).

This module only *builds* the router; ``bizora.main`` mounts it over
the shared bus (``bizora.streaming.bus.get_shared_bus``), which
``bizora.api`` also injects into the execution worker. The worker
publishes a RUNNING state event on claim, one metric event per
adapter-reported metric, and a terminal state event on finalize, which
ends the stream.

Endpoints:

- ``GET /api/v1/experiments/runs/{run_id}/telemetry/stream``:
  ``text/event-stream`` of ``id``/``event``/``data`` frames. ``from_seq``
  resumes from a cursor. Heartbeat comments keep the connection alive;
  the stream ends after the terminal state event.
- ``GET /api/v1/experiments/runs/{run_id}/telemetry/events``:
  JSON replay of buffered events (debugging and non-stream clients).
"""

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse

from bizora.contracts.run import ExperimentRun
from bizora.contracts.streaming import TelemetryEvent
from bizora.streaming.bus import TelemetryBus
from bizora.streaming.sse import (
    SSE_CONTENT_TYPE,
    format_event,
    format_heartbeat,
)

#: Loader injected by the owner so the router can 404 unknown runs
#: without importing the database layer itself.
RunLoader = Callable[[str], ExperimentRun | None]


def _run_not_found(run_id: str) -> JSONResponse:
    """Return the Bizora-shaped 404 for an unknown run."""
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Run '{run_id}' was not found.",
                "details": {"run_id": run_id},
            }
        },
    )


def create_streaming_router(
    bus: TelemetryBus,
    *,
    get_run: RunLoader | None = None,
    heartbeat_seconds: float = 15.0,
) -> APIRouter:
    """Build the telemetry router over one shared bus."""
    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive.")
    router = APIRouter(tags=["telemetry"])

    def _unknown_run(run_id: str) -> bool:
        """Return True when the injected loader knows no such run."""
        return get_run is not None and get_run(run_id) is None

    @router.get(
        "/api/v1/experiments/runs/{run_id}/telemetry/stream",
        response_class=StreamingResponse,
        response_model=None,
    )
    def stream_run_telemetry(
        run_id: str,
        from_seq: int = Query(default=0, ge=0),
    ) -> StreamingResponse | JSONResponse:
        """Stream one run's telemetry as Server-Sent Events."""
        if _unknown_run(run_id):
            return _run_not_found(run_id)

        def event_iterator() -> Iterator[str]:
            """Replay buffered events, then tail live ones to terminal."""
            subscription = bus.subscribe(run_id, from_seq=from_seq)
            try:
                while True:
                    event = subscription.poll(timeout_seconds=heartbeat_seconds)
                    if event is None:
                        if subscription.done:
                            return
                        yield format_heartbeat()
                    else:
                        yield format_event(event)
            finally:
                subscription.close()

        return StreamingResponse(
            event_iterator(),
            media_type=SSE_CONTENT_TYPE,
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get(
        "/api/v1/experiments/runs/{run_id}/telemetry/events",
        response_model=list[TelemetryEvent],
    )
    def list_telemetry_events(
        run_id: str,
        from_seq: int = Query(default=0, ge=0),
    ) -> list[TelemetryEvent] | JSONResponse:
        """Return buffered telemetry events as JSON (oldest first)."""
        if _unknown_run(run_id):
            return _run_not_found(run_id)
        return list(bus.replay(run_id, from_seq=from_seq))

    return router
