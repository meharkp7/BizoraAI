"""Thread-safe in-memory broadcast bus for run telemetry.

One process hosts one :class:`TelemetryBus` (injected into the router).
The execution worker publishes sequenced events; each SSE subscriber
first replays buffered events from its ``from_seq`` cursor and then
tails live ones. Publishing a terminal lifecycle event (succeeded,
failed, cancelled) or calling :meth:`TelemetryBus.close_run` ends the
stream: subscribers drain the buffer and then observe ``done``. Stopping
a run must therefore publish its terminal state or close the run, which
is owner wiring in the execution service.

Sequence discipline: ``seq`` must increase strictly within a run, so a
reconnecting browser can resume from its last ``id`` without gaps or
duplicates.
"""

import queue
import threading
from collections import deque
from contextlib import suppress

from bizora.contracts.run import TERMINAL_STATES, RunState
from bizora.contracts.streaming import TelemetryEvent, TelemetryEventKind

#: Upper bound on buffered events per run; publishing past it fails
#: loudly instead of growing memory without limit.
MAX_BUFFERED_PER_RUN = 10_000


class _Closed:
    """Sentinel marking the end of a run's stream."""

    __slots__ = ()


_CLOSED = _Closed()


class TelemetrySubscription:
    """One subscriber's replay-plus-live view of a run's stream."""

    def __init__(
        self,
        run_id: str,
        replay: deque[TelemetryEvent],
        live: queue.Queue[TelemetryEvent | _Closed],
        bus: "TelemetryBus",
    ) -> None:
        self._run_id = run_id
        self._replay = replay
        self._live = live
        self._bus = bus
        self._closed = False
        self._done = False

    @property
    def run_id(self) -> str:
        """Return the subscribed run id."""
        return self._run_id

    @property
    def done(self) -> bool:
        """Return True once the stream ended and is fully drained."""
        return self._done

    def poll(self, timeout_seconds: float) -> TelemetryEvent | None:
        """Return the next event, or None on timeout or end-of-stream.

        Callers distinguish the two by checking :attr:`done` after a
        None: done means the stream ended (terminal state or explicit
        close), otherwise the caller should retry (or send a heartbeat).
        """
        if self._done:
            return None
        if self._replay:
            return self._replay.popleft()
        if self._closed:
            self._done = True
            return None
        try:
            item = self._live.get(timeout=timeout_seconds)
        except queue.Empty:
            return None
        if isinstance(item, _Closed):
            self._closed = True
            self._done = True
            return None
        return item

    def close(self) -> None:
        """Detach from the bus; safe to call more than once."""
        self._bus.unsubscribe(self)


class TelemetryBus:
    """Publish/subscribe fan-out for per-run telemetry streams."""

    def __init__(self, *, max_buffered_per_run: int = MAX_BUFFERED_PER_RUN) -> None:
        if max_buffered_per_run < 1:
            raise ValueError("max_buffered_per_run must be positive.")
        self._max_buffered = max_buffered_per_run
        self._lock = threading.Lock()
        self._buffers: dict[str, list[TelemetryEvent]] = {}
        self._subscribers: dict[str, list[queue.Queue[TelemetryEvent | _Closed]]] = {}
        self._closed_runs: set[str] = set()

    def next_seq(self, run_id: str) -> int:
        """Return the next sequence number for a run (race-safe)."""
        with self._lock:
            buffered = self._buffers.get(run_id, [])
            if not buffered:
                return 0
            return buffered[-1].seq + 1

    def publish(self, event: TelemetryEvent) -> TelemetryEvent:
        """Append one event and fan it out to live subscribers."""
        with self._lock:
            if event.run_id in self._closed_runs:
                raise ValueError(f"Run '{event.run_id}' stream is closed.")
            buffered = self._buffers.setdefault(event.run_id, [])
            if buffered and event.seq <= buffered[-1].seq:
                raise ValueError(
                    f"Event seq {event.seq} must exceed "
                    f"{buffered[-1].seq} for run '{event.run_id}'."
                )
            if len(buffered) >= self._max_buffered:
                raise ValueError(
                    f"Run '{event.run_id}' exceeded {self._max_buffered} buffered events."
                )
            buffered.append(event)
            targets = list(self._subscribers.get(event.run_id, []))
            terminal = self._is_terminal_event(event)
            if terminal:
                self._closed_runs.add(event.run_id)
        for target in targets:
            target.put(event)
            if terminal:
                target.put(_CLOSED)
        return event

    def replay(self, run_id: str, *, from_seq: int = 0) -> tuple[TelemetryEvent, ...]:
        """Return buffered events at or after ``from_seq``."""
        if from_seq < 0:
            raise ValueError("from_seq must be non-negative.")
        with self._lock:
            buffered = self._buffers.get(run_id, [])
            return tuple(event for event in buffered if event.seq >= from_seq)

    def subscribe(self, run_id: str, *, from_seq: int = 0) -> TelemetrySubscription:
        """Subscribe to a run, replaying from ``from_seq`` then live."""
        if from_seq < 0:
            raise ValueError("from_seq must be non-negative.")
        live: queue.Queue[TelemetryEvent | _Closed] = queue.Queue()
        with self._lock:
            buffered = self._buffers.get(run_id, [])
            replay = deque(event for event in buffered if event.seq >= from_seq)
            if run_id in self._closed_runs:
                # Terminal streams serve the replay only; poll() drains
                # it and then reports done without blocking on live.
                subscription = TelemetrySubscription(run_id, replay, live, self)
                subscription._closed = True
                return subscription
            self._subscribers.setdefault(run_id, []).append(live)
            return TelemetrySubscription(run_id, replay, live, self)

    def unsubscribe(self, subscription: TelemetrySubscription) -> None:
        """Detach one subscription from live fan-out."""
        with self._lock:
            targets = self._subscribers.get(subscription.run_id)
            if targets is None:
                return
            with suppress(ValueError):
                targets.remove(subscription._live)  # noqa: SLF001 - owned internals.
            if not targets:
                self._subscribers.pop(subscription.run_id, None)

    def close_run(self, run_id: str) -> None:
        """End a run's stream; buffered events remain replayable.

        This is the wiring point for run cancellation: stopping a run
        must close its stream so browsers stop waiting.
        """
        with self._lock:
            if run_id in self._closed_runs:
                return
            self._closed_runs.add(run_id)
            targets = list(self._subscribers.get(run_id, []))
        for target in targets:
            target.put(_CLOSED)

    def is_closed(self, run_id: str) -> bool:
        """Return whether a run's stream has ended."""
        with self._lock:
            return run_id in self._closed_runs

    @staticmethod
    def _is_terminal_event(event: TelemetryEvent) -> bool:
        """Return True for lifecycle events in a terminal state."""
        if event.kind != TelemetryEventKind.STATE or event.state is None:
            return False
        state: RunState = event.state.state
        return state in TERMINAL_STATES


_SHARED_BUS: TelemetryBus | None = None
_SHARED_BUS_LOCK = threading.Lock()


def get_shared_bus() -> TelemetryBus:
    """Return the process-wide bus shared by the worker and the router.

    ``bizora.api`` injects this into the execution worker and
    ``bizora.main`` injects it into the streaming router so live SSE
    subscribers observe the same events the worker publishes. Tests
    that need isolation construct their own :class:`TelemetryBus`.
    """
    global _SHARED_BUS
    with _SHARED_BUS_LOCK:
        if _SHARED_BUS is None:
            _SHARED_BUS = TelemetryBus()
        return _SHARED_BUS
