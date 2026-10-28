"""Derive paper-reported metrics from extracted results tables.

Names-driven and conservative: the caller names the metrics it wants
(usually the measured names from a run comparison) and each table is
scanned for exact header/label matches in both table orientations — a
metric in a column header with values below it, or a metric in a row
label with values beside it. Matching is case-insensitive with one
documented normalization (a single trailing parenthetical such as a
unit is ignored); returned entries carry the REQUESTED name so the
exact-name comparison join lines up, while raw_value, quote, and
locator preserve the paper's own text and position. A matched header
or label emits entries only when at least one of its value cells
parses numeric, so label columns never masquerade as metrics.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from bizora.contracts.streaming import PaperReportedMetric
from bizora.contracts.table import ExtractedTable

_UNIT_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")

_NUMBER = r"[+-]?(?:\d[\d,]*\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_VALUE_RE = re.compile(rf"^\s*({_NUMBER})(?:\s*±\s*{_NUMBER})?\s*(%?)\s*$")


def _match_key(text: str) -> str:
    """Normalize one header or label for metric-name matching."""
    return _UNIT_PAREN_RE.sub("", text.strip().lower()).strip()


def _parse_value(cell: str) -> tuple[float | None, str | None]:
    """Split one cell into a finite parsed value and unit, if unambiguous."""
    match = _VALUE_RE.match(cell)
    if match is None:
        return None, None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, None
    if not math.isfinite(value):
        return None, None
    unit = match.group(2) or None
    return value, unit if unit else None


def _short(text: str, limit: int) -> str:
    """Truncate evidence text to a contract-safe length."""
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def _entry(
    name: str,
    cell: str,
    table: ExtractedTable,
    *,
    quote: str,
    locator: str,
) -> PaperReportedMetric:
    """Build one grounded entry from a matched cell."""
    value, unit = _parse_value(cell)
    return PaperReportedMetric(
        name=name,
        raw_value=_short(cell, 128),
        value=value,
        unit=unit,
        source_id=table.source_id,
        table_id=table.table_id,
        page=table.page,
        quote=_short(quote, 2000),
        locator=_short(locator, 512),
    )


def reported_metrics_for_tables(
    tables: Sequence[ExtractedTable],
    names: Sequence[str],
) -> tuple[PaperReportedMetric, ...]:
    """Quote the named metrics from every table, deduplicated."""
    wanted: dict[str, str] = {}
    for name in names:
        cleaned = name.strip()
        if cleaned:
            wanted.setdefault(_match_key(cleaned), cleaned)
    if not wanted:
        return ()
    entries: list[PaperReportedMetric] = []
    seen: set[tuple[str, str, str]] = set()
    for table in tables:
        for entry in _scan_table(table, wanted):
            key = (entry.name, entry.raw_value, entry.locator or "")
            if key not in seen:
                seen.add(key)
                entries.append(entry)
    return tuple(entries)


def _scan_table(
    table: ExtractedTable,
    wanted: dict[str, str],
) -> list[PaperReportedMetric]:
    """Scan one table in both orientations for the wanted names."""
    found: list[PaperReportedMetric] = []
    columns = list(table.columns)
    rows = [list(row) for row in table.rows]
    for index, header in enumerate(columns):
        name = wanted.get(_match_key(header))
        if name is not None:
            found.extend(_column_entries(table, columns, rows, name, header, index))
    for number, row in enumerate(rows):
        if not row:
            continue
        name = wanted.get(_match_key(row[0]))
        if name is not None:
            found.extend(_row_entries(table, columns, row, name, number))
    return found


def _column_entries(
    table: ExtractedTable,
    columns: list[str],
    rows: list[list[str]],
    name: str,
    header: str,
    column: int,
) -> list[PaperReportedMetric]:
    """Quote one matched column's cells, when any parses numeric."""
    cells = [(number, row[column]) for number, row in enumerate(rows) if column < len(row)]
    if not any(_parse_value(cell)[0] is not None for _, cell in cells):
        return []
    entries: list[PaperReportedMetric] = []
    for number, cell in cells:
        if not cell.strip():
            continue
        label = rows[number][0].strip() if rows[number] else ""
        entries.append(
            _entry(
                name,
                cell,
                table,
                quote=f"{label}: {cell.strip()} ({header.strip()})" if label else cell.strip(),
                locator=(
                    f"Table {table.table_id}: column '{_short(header, 60)}' "
                    f"row {number + 1} ('{_short(label, 60)}')"
                ),
            )
        )
    return entries


def _row_entries(
    table: ExtractedTable,
    columns: list[str],
    row: list[str],
    name: str,
    number: int,
) -> list[PaperReportedMetric]:
    """Quote one matched row's cells, when any parses numeric."""
    cells = list(enumerate(row))[1:]
    if not any(_parse_value(cell)[0] is not None for _, cell in cells):
        return []
    label = row[0].strip()
    entries: list[PaperReportedMetric] = []
    for column, cell in cells:
        if not cell.strip():
            continue
        header = columns[column] if column < len(columns) else f"col {column + 1}"
        entries.append(
            _entry(
                name,
                cell,
                table,
                quote=f"{label}: {cell.strip()} ({header.strip()})",
                locator=(
                    f"Table {table.table_id}: row '{_short(label, 60)}' "
                    f"column '{_short(header, 60)}'"
                ),
            )
        )
    return entries
