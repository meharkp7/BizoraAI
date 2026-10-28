"""Local ngspice batch execution and measurement parsing.

The runner shells out to a real ngspice binary in batch mode, captures
its merged output under caller-supplied time and byte caps, and parses
``name = value`` measurement lines. Parsing is fully generic: no
measurement or node names are hard-coded, so any ``print`` or ``.meas``
directive carried in graph data flows through as a metric.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Runner data: binary candidates and output patterns.
# ---------------------------------------------------------------------------

NGSPICE_CANDIDATES: tuple[str, ...] = ("/opt/homebrew/bin/ngspice", "ngspice")

ERROR_PREFIX = "Error:"
FAILED_MEAS_PATTERN = re.compile(r"^\s*([A-Za-z_][\w.()#:\-]*)\s*=\s*failed\b", re.IGNORECASE)
MEASUREMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z_][\w.()#:\-]*)\s*=\s*"
    r"([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
)


@dataclass(frozen=True)
class NgspiceMeasurement:
    """One parsed ``name = value`` line from ngspice output."""

    name: str
    value: float


@dataclass(frozen=True)
class NgspiceRun:
    """Outcome of one batch ngspice invocation."""

    returncode: int
    timed_out: bool
    truncated: bool
    measurements: tuple[NgspiceMeasurement, ...]
    errors: tuple[str, ...]
    failed_measurements: tuple[str, ...]
    output_bytes: int


def resolve_ngspice() -> str | None:
    """Return the first usable ngspice binary, or None when absent."""
    for candidate in NGSPICE_CANDIDATES:
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
            continue
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    return None


def parse_measurements(output: str) -> tuple[NgspiceMeasurement, ...]:
    """Parse every ``name = value`` line, keeping the first per name."""
    seen: set[str] = set()
    parsed: list[NgspiceMeasurement] = []
    for line in output.splitlines():
        match = MEASUREMENT_PATTERN.match(line)
        if match is None:
            continue
        name = match.group(1)
        if name in seen:
            continue
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        seen.add(name)
        parsed.append(NgspiceMeasurement(name=name, value=value))
    return tuple(parsed)


def parse_errors(output: str) -> tuple[str, ...]:
    """Collect ngspice ``Error:`` lines in order, deduplicated."""
    errors: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(ERROR_PREFIX) and stripped not in errors:
            errors.append(stripped)
    return tuple(errors)


def parse_failed_measurements(output: str) -> tuple[str, ...]:
    """Collect measurement names ngspice reports as failed."""
    failed: list[str] = []
    for line in output.splitlines():
        match = FAILED_MEAS_PATTERN.match(line)
        if match is not None and match.group(1) not in failed:
            failed.append(match.group(1))
    return tuple(failed)


def run_netlist(
    netlist_text: str,
    *,
    executable: str,
    timeout_seconds: int,
    max_output_bytes: int,
) -> NgspiceRun:
    """Run one netlist through ngspice batch mode and parse its output."""
    with tempfile.TemporaryDirectory(prefix="bizora-ngspice-") as tmpdir:
        circuit_path = os.path.join(tmpdir, "circuit.cir")
        with open(circuit_path, "w", encoding="utf-8") as handle:
            handle.write(netlist_text)
        try:
            completed = subprocess.run(
                [executable, "-b", circuit_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=max(timeout_seconds, 1),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or b"")[: max(max_output_bytes, 1)]
            output = partial.decode("utf-8", errors="replace")
            return NgspiceRun(
                returncode=-1,
                timed_out=True,
                truncated=True,
                measurements=parse_measurements(output),
                errors=parse_errors(output),
                failed_measurements=parse_failed_measurements(output),
                output_bytes=len(partial),
            )
        raw = completed.stdout or b""
        truncated = len(raw) > max(max_output_bytes, 1)
        output = raw[: max(max_output_bytes, 1)].decode("utf-8", errors="replace")
        return NgspiceRun(
            returncode=completed.returncode,
            timed_out=False,
            truncated=truncated,
            measurements=parse_measurements(output),
            errors=parse_errors(output),
            failed_measurements=parse_failed_measurements(output),
            output_bytes=len(raw),
        )
