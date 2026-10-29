"""The R9 copilot tool set: read-only tools plus patch proposal.

Every tool reads state the caller supplies through
:class:`CopilotContext` and returns JSON-serializable data. No tool
writes anything: ``propose_patch`` builds a
:class:`CopilotProposal` object that waits for explicit human
approval, exactly like the deterministic copilot path. Tool names,
descriptions, and schemas carry no domain, paper, or part names;
concrete values arrive only as call arguments and results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bizora.contracts.components import CopilotProposal
from bizora.contracts.figures import PaperFigure
from bizora.contracts.graph import MethodologyGraph
from bizora.contracts.run import ExperimentRun, MetricRecord
from bizora.contracts.table import ExtractedTable
from bizora.copilot.pack_tools import execute_pack_tool
from bizora.core.component_catalog import get_component, search_components
from bizora.core.component_service import (
    build_replacement_node,
    preflight_removal,
    preflight_replacement,
)
from bizora.core.diff_service import RevisionDiffService
from bizora.core.errors import BizoraError
from bizora.core.reported_service import reported_metrics_for_tables
from bizora.packs.base import DomainPack
from bizora.providers.copilot import CopilotToolSpec


@dataclass
class CopilotContext:
    """Everything the tools may read for one copilot question."""

    graph: MethodologyGraph
    selected_node_id: str | None = None
    load_revision: Callable[[int], MethodologyGraph | None] | None = None
    list_runs: Callable[[], list[ExperimentRun]] | None = None
    get_run: Callable[[str], ExperimentRun | None] | None = None
    list_metrics: Callable[[str], list[MetricRecord]] | None = None
    list_tables: Callable[[], list[ExtractedTable]] | None = None
    list_figures: Callable[[], list[PaperFigure]] | None = None
    write_log: list[str] = field(default_factory=list)
    pack: DomainPack | None = None

    def revisions(self, version: int) -> MethodologyGraph | None:
        """Load one revision, defaulting to the current graph."""
        if version == self.graph.version:
            return self.graph
        if self.load_revision is None:
            return None
        return self.load_revision(version)

    def runs(self) -> list[ExperimentRun]:
        """List runs visible to this question."""
        if self.list_runs is None:
            return []
        return self.list_runs()

    def run(self, run_id: str) -> ExperimentRun | None:
        """Fetch one run by id."""
        if self.get_run is not None:
            return self.get_run(run_id)
        return next((run for run in self.runs() if run.run_id == run_id), None)

    def metrics(self, run_id: str) -> list[MetricRecord]:
        """List metrics recorded for one run."""
        if self.list_metrics is None:
            return []
        return self.list_metrics(run_id)

    def tables(self) -> list[ExtractedTable]:
        """List extracted results tables visible to this question."""
        if self.list_tables is None:
            return []
        return self.list_tables()

    def figures(self) -> list[PaperFigure]:
        """List ingested paper figures visible to this question."""
        if self.list_figures is None:
            return []
        return self.list_figures()


def _node_payload(graph: MethodologyGraph, node_id: str) -> dict[str, Any] | None:
    node = next((n for n in graph.nodes if n.id == node_id), None)
    if node is None:
        return None
    return {
        "id": node.id,
        "kind": node.kind.value,
        "label": node.label,
        "description": node.description,
        "config": dict(node.config),
        "provenance": node.provenance.value,
        "confidence": node.confidence,
        "evidence": [ref.model_dump(mode="json") for ref in node.evidence],
    }


def _edge_payload(graph: MethodologyGraph, edge_id: str) -> dict[str, Any] | None:
    edge = next((e for e in graph.edges if e.id == edge_id), None)
    if edge is None:
        return None
    return {
        "id": edge.id,
        "source": edge.source,
        "target": edge.target,
        "relation": edge.relation.value,
        "label": edge.label,
        "provenance": edge.provenance.value,
        "evidence": [ref.model_dump(mode="json") for ref in edge.evidence],
    }


def tool_search_library(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the component library for catalog entries."""
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string."}
    limit = arguments.get("limit", 5)
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        return {"error": "limit must be an integer between 1 and 20."}
    results = search_components(query.strip(), limit=limit)
    return {
        "query": query.strip(),
        "matches": [
            {
                "component_id": hit.component_id,
                "label": hit.label,
                "domain": hit.domain,
                "category": hit.category,
                "kind": hit.kind,
                "generic": hit.generic,
                "manufacturer": hit.manufacturer,
                "part_number": hit.part_number,
                "headline": hit.headline,
            }
            for hit in results
        ],
    }


def tool_read_evidence(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Read paper evidence attached to one node or edge."""
    target_id = arguments.get("target_id")
    if not isinstance(target_id, str) or not target_id.strip():
        return {"error": "target_id must be a non-empty node or edge id."}
    cleaned = target_id.strip()
    node = _node_payload(context.graph, cleaned)
    if node is not None:
        return {"target_type": "node", "target": node}
    edge = _edge_payload(context.graph, cleaned)
    if edge is not None:
        return {"target_type": "edge", "target": edge}
    if context.selected_node_id and cleaned.lower() in ("this", "selected", "it"):
        node = _node_payload(context.graph, context.selected_node_id)
        if node is not None:
            return {"target_type": "node", "target": node}
    return {"error": f"No node or edge has id {cleaned!r} in this revision."}


def tool_inspect_graph(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Summarize the graph revision structure."""
    scope = arguments.get("scope", "summary")
    if scope not in ("summary", "nodes", "edges"):
        return {"error": "scope must be one of: summary, nodes, edges."}
    graph = context.graph
    payload: dict[str, Any] = {
        "project_id": graph.project_id,
        "graph_id": graph.graph_id,
        "version": graph.version,
        "title": graph.title,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "source_ids": list(graph.source_ids),
    }
    if scope in ("summary", "nodes"):
        payload["nodes"] = [
            {
                "id": node.id,
                "kind": node.kind.value,
                "label": node.label,
                "provenance": node.provenance.value,
                "evidence_count": len(node.evidence),
            }
            for node in graph.nodes
        ]
    if scope in ("summary", "edges"):
        payload["edges"] = [
            {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "relation": edge.relation.value,
                "label": edge.label,
            }
            for edge in graph.edges
        ]
    return payload


def tool_diff_revisions(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Diff two revisions of the current graph."""
    base = arguments.get("base_version")
    target = arguments.get("target_version", context.graph.version)
    if not isinstance(base, int) or not isinstance(target, int):
        return {"error": "base_version and target_version must be integers."}
    base_graph = context.revisions(base)
    target_graph = context.revisions(target)
    if base_graph is None:
        return {"error": f"Revision {base} is not available."}
    if target_graph is None:
        return {"error": f"Revision {target} is not available."}
    try:
        diff = RevisionDiffService.diff(base_graph, target_graph)
    except BizoraError as exc:
        return {"error": str(exc)}
    return {
        "base_version": base,
        "target_version": target,
        "added_nodes": [n.id for n in diff.added_nodes],
        "removed_nodes": [n.id for n in diff.removed_nodes],
        "changed_nodes": [c.node_id for c in diff.changed_nodes],
        "added_edges": [e.id for e in diff.added_edges],
        "removed_edges": [e.id for e in diff.removed_edges],
        "changed_edges": [c.edge_id for c in diff.changed_edges],
    }


def tool_query_runs(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query experiment run status, metrics, and errors."""
    run_id = arguments.get("run_id")
    if run_id is not None:
        if not isinstance(run_id, str) or not run_id.strip():
            return {"error": "run_id must be a non-empty string."}
        run = context.run(run_id.strip())
        if run is None:
            return {"error": f"No run has id {run_id.strip()!r}."}
        runs = [run]
    else:
        limit = arguments.get("limit", 10)
        if not isinstance(limit, int) or not 1 <= limit <= 50:
            return {"error": "limit must be an integer between 1 and 50."}
        runs = context.runs()[:limit]
    payload_runs: list[dict[str, Any]] = []
    for run in runs:
        metrics = context.metrics(run.run_id)
        payload_runs.append(
            {
                "run_id": run.run_id,
                "state": run.state.value,
                "graph_version": run.config.graph_version,
                "adapter_id": run.config.adapter_id,
                "created_at": run.created_at.isoformat(),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "error": run.error,
                "metrics": [
                    {
                        "name": metric.name,
                        "value": metric.value,
                        "result_kind": metric.result_kind.value,
                    }
                    for metric in metrics
                ],
            }
        )
    return {"runs": payload_runs}


def tool_run_preflight(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate a catalog replacement against one node without writing."""
    node_id = arguments.get("node_id")
    component_id = arguments.get("component_id")
    if not isinstance(node_id, str) or not node_id.strip():
        return {"error": "node_id must be a non-empty string."}
    if not isinstance(component_id, str) or not component_id.strip():
        return {"error": "component_id must be a non-empty catalog id."}
    config = arguments.get("config", {})
    if not isinstance(config, dict):
        return {"error": "config must be an object."}
    try:
        preflight = preflight_replacement(
            context.graph, node_id.strip(), component_id.strip(), dict(config)
        )
    except BizoraError as exc:
        return {"error": str(exc)}
    return {
        "compatible": preflight.compatible,
        "target_node_id": preflight.target_node_id,
        "component_id": preflight.component_id,
        "candidate_label": preflight.candidate_label,
        "preserved_edge_ids": list(preflight.preserved_edge_ids),
        "missing_interfaces": [
            {"kind": missing.kind, "reason": missing.reason}
            for missing in preflight.missing_interfaces
        ],
        "warnings": [
            {"code": warning.code, "message": warning.message} for warning in preflight.warnings
        ],
    }


def tool_run_removal_preflight(
    context: CopilotContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Preview removing one node: neighbors, dropped edges, paper claims."""
    node_id = arguments.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        return {"error": "node_id must be a non-empty string."}
    try:
        preflight = preflight_removal(context.graph, node_id.strip())
    except BizoraError as exc:
        return {"error": str(exc)}
    return {
        "target_node_id": preflight.target_node_id,
        "neighbor_node_ids": list(preflight.neighbor_node_ids),
        "dropped_edge_ids": list(preflight.dropped_edge_ids),
        "evidence": [ref.model_dump(mode="json") for ref in preflight.evidence],
    }


def tool_propose_patch(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a patch proposal for human approval; never applies it."""
    node_id = arguments.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        return {"error": "node_id must be a non-empty string."}
    node = next((n for n in context.graph.nodes if n.id == node_id.strip()), None)
    if node is None:
        return {"error": f"No node has id {node_id.strip()!r} in this revision."}
    component_id = arguments.get("component_id")
    if component_id is not None and (not isinstance(component_id, str) or not component_id.strip()):
        return {"error": "component_id must be a non-empty catalog id or null."}
    config = arguments.get("config", {})
    if not isinstance(config, dict):
        return {"error": "config must be an object."}
    rationale = arguments.get("rationale", "")
    if not isinstance(rationale, str) or not rationale.strip():
        return {"error": "rationale must be a non-empty string."}

    if component_id is not None:
        detail = get_component(component_id.strip())
        if detail is None:
            return {"error": f"No catalog entry has id {component_id.strip()!r}."}
        try:
            replacement = build_replacement_node(node, detail)
        except BizoraError as exc:
            return {"error": str(exc)}
        merged_config = {**replacement.config, **dict(config)}
        proposal = CopilotProposal(
            node_id=node.id,
            component_id=detail.component_id,
            kind=detail.kind,
            label=detail.label,
            description=detail.description,
            config=merged_config,
            rationale=rationale.strip()[:1000],
        )
    else:
        merged = {**node.config, **dict(config)}
        proposal = CopilotProposal(
            node_id=node.id,
            component_id=None,
            kind=node.kind.value,
            label=node.label,
            description=node.description,
            config=merged,
            rationale=rationale.strip()[:1000],
        )
    return {
        "proposal": proposal.model_dump(mode="json"),
        "status": "pending_approval",
        "note": "Nothing was changed. The human must approve this proposal.",
    }


MAX_TABLE_ROWS_PER_TOOL_CALL = 12


def _short_text(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit]


def tool_read_tables(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Read the paper's extracted results tables, optionally one table."""
    tables = context.tables()
    if not tables:
        return {"tables": [], "note": "No results tables were extracted for this graph."}
    wanted = arguments.get("table_id")
    if isinstance(wanted, str) and wanted.strip():
        tables = [table for table in tables if table.table_id == wanted.strip()]
        if not tables:
            return {"error": f"No table has id {wanted.strip()!r}."}
    payload = [
        {
            "table_id": table.table_id,
            "caption": table.caption,
            "page": table.page,
            "quote": table.quote,
            "columns": list(table.columns),
            "rows": [list(row) for row in table.rows[:MAX_TABLE_ROWS_PER_TOOL_CALL]],
            "truncated_rows": max(0, len(table.rows) - MAX_TABLE_ROWS_PER_TOOL_CALL),
        }
        for table in tables
    ]
    evidence = [
        {
            "source_id": table.source_id,
            "page": table.page,
            "quote": _short_text(f"{table.caption} {table.quote or ''}", 2000),
            "figure_label": None,
        }
        for table in tables
    ]
    return {"tables": payload, "target": {"id": "tables", "evidence": evidence}}


def tool_read_figures(context: CopilotContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Read the paper's ingested figures with their localized regions."""
    figures = context.figures()
    if not figures:
        return {"figures": [], "note": "No figures were ingested for this graph."}
    wanted = arguments.get("figure_id")
    if isinstance(wanted, str) and wanted.strip():
        figures = [figure for figure in figures if figure.figure_id == wanted.strip()]
        if not figures:
            return {"error": f"No figure has id {wanted.strip()!r}."}
    payload = [
        {
            "figure_id": figure.figure_id,
            "label": figure.label,
            "kind": figure.kind.value,
            "page": figure.page,
            "caption": _short_text(figure.caption or "", 1200),
            "regions": [
                {"label": region.label, "node_id": region.node_id}
                for region in figure.regions
            ],
        }
        for figure in figures
    ]
    evidence = [
        {
            "source_id": figure.source_id,
            "page": figure.page,
            "quote": _short_text(figure.caption or figure.label or "", 2000) or None,
            "figure_label": figure.label,
        }
        for figure in figures
    ]
    return {"figures": payload, "target": {"id": "figures", "evidence": evidence}}


def tool_quote_reported(
    context: CopilotContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Quote the paper's reported numbers for named metrics."""
    names = arguments.get("names")
    if not isinstance(names, list) or not names:
        return {"error": "names must be a non-empty list of metric names."}
    cleaned = [name.strip() for name in names if isinstance(name, str) and name.strip()]
    if not cleaned:
        return {"error": "names must be a non-empty list of metric names."}
    tables = context.tables()
    if not tables:
        return {"entries": [], "note": "No results tables were extracted for this graph."}
    entries = reported_metrics_for_tables(tables, cleaned)
    evidence = [
        {
            "source_id": entry.source_id,
            "page": entry.page,
            "quote": entry.quote,
            "figure_label": None,
        }
        for entry in entries
    ]
    return {
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "target": {"id": "reported-metrics", "evidence": evidence},
    }


TOOL_HANDLERS = {
    "search_library": tool_search_library,
    "read_evidence": tool_read_evidence,
    "inspect_graph": tool_inspect_graph,
    "diff_revisions": tool_diff_revisions,
    "query_runs": tool_query_runs,
    "run_preflight": tool_run_preflight,
    "run_removal_preflight": tool_run_removal_preflight,
    "propose_patch": tool_propose_patch,
    "read_tables": tool_read_tables,
    "read_figures": tool_read_figures,
    "quote_reported": tool_quote_reported,
}


def _string_prop(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


TOOL_SPECS: tuple[CopilotToolSpec, ...] = (
    CopilotToolSpec(
        name="search_library",
        description="Search the component library for replacement parts or techniques.",
        parameters={
            "type": "object",
            "properties": {
                "query": _string_prop("Free-text search over the catalog."),
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["query"],
        },
    ),
    CopilotToolSpec(
        name="read_evidence",
        description="Read the paper evidence attached to one graph node or edge.",
        parameters={
            "type": "object",
            "properties": {
                "target_id": _string_prop("Node or edge id to inspect."),
            },
            "required": ["target_id"],
        },
    ),
    CopilotToolSpec(
        name="inspect_graph",
        description="Summarize the current graph revision structure.",
        parameters={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["summary", "nodes", "edges"],
                    "default": "summary",
                },
            },
        },
    ),
    CopilotToolSpec(
        name="diff_revisions",
        description="Diff two revisions of the current graph.",
        parameters={
            "type": "object",
            "properties": {
                "base_version": {"type": "integer", "minimum": 1},
                "target_version": {"type": "integer", "minimum": 1},
            },
            "required": ["base_version"],
        },
    ),
    CopilotToolSpec(
        name="query_runs",
        description="Query experiment run status, metrics, and errors.",
        parameters={
            "type": "object",
            "properties": {
                "run_id": _string_prop("One run to inspect; omit to list recent runs."),
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
        },
    ),
    CopilotToolSpec(
        name="run_preflight",
        description="Validate a catalog replacement against one node without writing.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": _string_prop("Graph node id to replace."),
                "component_id": _string_prop("Catalog component id to validate."),
                "config": {"type": "object", "description": "Optional config overrides."},
            },
            "required": ["node_id", "component_id"],
        },
    ),
    CopilotToolSpec(
        name="run_removal_preflight",
        description="Preview removing one node: neighbors, dropped edges, paper claims.",
        parameters={
            "type": "object",
            "properties": {
                "node_id": _string_prop("Graph node id to hypothetically remove."),
            },
            "required": ["node_id"],
        },
    ),
    CopilotToolSpec(
        name="propose_patch",
        description=("Build a patch proposal for human approval. Never applies anything."),
        parameters={
            "type": "object",
            "properties": {
                "node_id": _string_prop("Graph node id to change."),
                "component_id": _string_prop(
                    "Catalog component id for replacements; omit for config-only edits."
                ),
                "config": {"type": "object", "description": "Config values to set."},
                "rationale": _string_prop("Why this change is suggested."),
            },
            "required": ["node_id", "rationale"],
        },
    ),
    CopilotToolSpec(
        name="read_tables",
        description="Read the paper's extracted results tables.",
        parameters={
            "type": "object",
            "properties": {
                "table_id": _string_prop("One table to read; omit to list all tables."),
            },
        },
    ),
    CopilotToolSpec(
        name="read_figures",
        description="Read the paper's figures with localized component regions.",
        parameters={
            "type": "object",
            "properties": {
                "figure_id": _string_prop("One figure to read; omit to list all figures."),
            },
        },
    ),
    CopilotToolSpec(
        name="quote_reported",
        description="Quote the paper's reported numbers for named metrics.",
        parameters={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metric names to quote from the tables.",
                },
            },
            "required": ["names"],
        },
    ),
)


def execute_tool(context: CopilotContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one tool call against the context (read-only)."""
    handler = TOOL_HANDLERS.get(name)
    if handler is not None:
        try:
            return handler(context, arguments)
        except BizoraError as exc:
            return {"error": str(exc)}
    if context.pack is not None:
        packed = execute_pack_tool(context.pack, context, name, arguments)
        if packed is not None:
            return packed
    return {"error": f"Unknown tool {name!r}."}
