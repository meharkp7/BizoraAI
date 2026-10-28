"""Server-Sent Events encoding for telemetry.

Pure functions with no web-framework dependency, so the byte format is
unit-testable in isolation. The router streams
:meth:`format_event` frames and :meth:`format_heartbeat` comments.
"""

import json
from typing import Any

from bizora.contracts.streaming import TelemetryEvent

#: Media type for the telemetry stream response.
SSE_CONTENT_TYPE = "text/event-stream"

_HEARTBEAT_LINE = ": heartbeat"


def format_event(event: TelemetryEvent) -> str:
    """Encode one telemetry event as an SSE frame.

    The frame carries the stream cursor as ``id`` (the event seq), the
    telemetry kind as ``event`` (so browsers can subscribe per kind),
    and the full validated event JSON as ``data``.
    """
    payload = event.model_dump(mode="json")
    data = json.dumps(payload, sort_keys=True)
    return f"id: {event.seq}\nevent: {event.kind.value}\ndata: {data}\n\n"


def format_heartbeat() -> str:
    """Encode a keep-alive comment that browsers ignore."""
    return f"{_HEARTBEAT_LINE}\n\n"


def parse_event_frame(frame: str) -> tuple[int, str, dict[str, Any]]:
    """Decode one SSE frame into (id, event, data).

    Used by tests to assert the wire format round-trips; the browser
    uses the native EventSource parser instead.
    """
    event_id: int | None = None
    event_name: str | None = None
    data_lines: list[str] = []
    for line in frame.splitlines():
        if line.startswith("id:"):
            event_id = int(line[3:].strip())
        elif line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line == "" or line.startswith(":"):
            continue
        else:
            raise ValueError(f"Unexpected SSE line: {line!r}")
    if event_id is None or event_name is None or not data_lines:
        raise ValueError("SSE frame is missing id, event, or data.")
    data = json.loads("\n".join(data_lines))
    if not isinstance(data, dict):
        raise ValueError("SSE data must be a JSON object.")
    return event_id, event_name, data
