"""Head-to-head comparison of two graph revisions.

Pure function over stored revisions and tables: structure counts,
shared entity labels, and reported-metric overlap. Matching is
deliberately literal (case-insensitive labels, unit-stripped metric
names) so the arena never invents a correspondence.
"""

import re

from bizora.contracts.arena import (
    ArenaComparison,
    ArenaLabelOverlap,
    ArenaMetricRow,
    ArenaMetricValue,
    ArenaSideSummary,
    ArenaStructureSide,
    ArenaUniqueLabel,
)
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.streaming import PaperReportedMetric
from bizora.contracts.table import ExtractedTable
from bizora.core.reported_service import discover_reported_metrics

_UNIT_PAREN_RE = re.compile(r"\([^()]*\)\s*$")
MAX_METRIC_ROWS = 100
MAX_LABEL_ROWS = 200


def _label_key(label: str) -> str:
    """Normalize one entity label for cross-graph matching."""
    return " ".join(label.strip().lower().split())


def _metric_key_parts(name: str) -> set[str]:
    """Split one discovered name into matchable segments.

    Discovery joins row and column labels ("Ours — Accuracy"), so
    alignment works on either segment, ignoring units and case.
    """
    parts = set()
    for segment in name.split("—"):
        key = _UNIT_PAREN_RE.sub("", segment.strip().lower()).strip()
        if key:
            parts.add(key)
    return parts


def _structure(graph: MethodologyGraph) -> ArenaStructureSide:
    kinds: dict[str, int] = {}
    for node in graph.nodes:
        key = node.kind.value
        kinds[key] = kinds.get(key, 0) + 1
    return ArenaStructureSide(
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        kinds=dict(sorted(kinds.items())),
    )


def _labels(graph: MethodologyGraph) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Group one graph's node ids by normalized label, keeping display text."""
    grouped: dict[str, tuple[str, list[str]]] = {}
    for node in graph.nodes:
        key = _label_key(node.label)
        if not key:
            continue
        display, ids = grouped.get(key, (node.label, []))
        ids.append(node.id)
        grouped[key] = (display, ids)
    return {key: (display, tuple(ids)) for key, (display, ids) in grouped.items()}


def _metric_value(metric: PaperReportedMetric) -> ArenaMetricValue:
    return ArenaMetricValue(
        raw_value=metric.raw_value, value=metric.value, unit=metric.unit
    )


def compare_graphs(
    a_graph: MethodologyGraph,
    b_graph: MethodologyGraph,
    a_tables: list[ExtractedTable],
    b_tables: list[ExtractedTable],
) -> ArenaComparison:
    """Compare two revisions: structure, labels, and reported metrics."""
    a_labels = _labels(a_graph)
    b_labels = _labels(b_graph)
    shared = sorted(set(a_labels) & set(b_labels))
    only_a = sorted(set(a_labels) - set(b_labels))
    only_b = sorted(set(b_labels) - set(a_labels))

    a_metrics = sorted(discover_reported_metrics(a_tables), key=lambda m: m.name.lower())
    b_metrics = sorted(discover_reported_metrics(b_tables), key=lambda m: m.name.lower())
    b_parts = [_metric_key_parts(m.name) for m in b_metrics]
    used_b: set[int] = set()

    rows: list[ArenaMetricRow] = []
    for a_metric in a_metrics:
        parts = _metric_key_parts(a_metric.name)
        hit = next(
            (
                index
                for index, other in enumerate(b_parts)
                if index not in used_b and parts & other
            ),
            None,
        )
        if hit is None:
            rows.append(ArenaMetricRow(name=a_metric.name, a=_metric_value(a_metric)))
        else:
            used_b.add(hit)
            rows.append(
                ArenaMetricRow(
                    name=a_metric.name,
                    a=_metric_value(a_metric),
                    b=_metric_value(b_metrics[hit]),
                )
            )
    for index, b_metric in enumerate(b_metrics):
        if index not in used_b:
            rows.append(ArenaMetricRow(name=b_metric.name, b=_metric_value(b_metric)))
    rows.sort(key=lambda row: (row.a is None or row.b is None, row.name.lower()))

    return ArenaComparison(
        a=ArenaSideSummary(
            project_id=a_graph.project_id,
            graph_id=a_graph.graph_id,
            version=a_graph.version,
            title=a_graph.title,
        ),
        b=ArenaSideSummary(
            project_id=b_graph.project_id,
            graph_id=b_graph.graph_id,
            version=b_graph.version,
            title=b_graph.title,
        ),
        structure_a=_structure(a_graph),
        structure_b=_structure(b_graph),
        shared_labels=tuple(
            ArenaLabelOverlap(
                label=a_labels[key][0],
                a_node_ids=a_labels[key][1],
                b_node_ids=b_labels[key][1],
            )
            for key in shared[:MAX_LABEL_ROWS]
        ),
        unique_a=tuple(
            ArenaUniqueLabel(label=a_labels[key][0], node_ids=a_labels[key][1])
            for key in only_a[:MAX_LABEL_ROWS]
        ),
        unique_b=tuple(
            ArenaUniqueLabel(label=b_labels[key][0], node_ids=b_labels[key][1])
            for key in only_b[:MAX_LABEL_ROWS]
        ),
        metrics=tuple(rows[:MAX_METRIC_ROWS]),
    )
