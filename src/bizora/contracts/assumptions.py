"""Assumed-claim marking for extracted components and parts.

Rule zero applies: nothing here names a domain, paper, or part. When
extraction cannot ground a claim in the source, the claim is kept but
marked *assumed* with a human-readable reason, never presented as fact.

Storage: assumed flags travel inside the existing free-form ``config``
mapping of a graph node (``assumed`` / ``assumption_reason``), so the
marking persists visibly in the stored revision payload without any
change to the graph schema. Part mentions (which live outside the graph
as free-text references with parameter maps) use the same two keys.
Graph edges have no config mapping, so an edge is considered assumed
when it carries no evidence and its provenance is ``INFERRED``.

Two layers are provided:

* Strict Pydantic models (:class:`AssumptionFlag`,
  :class:`AssumedComponent`, :class:`AssumedPart`) for explicitly
  supplied markings. A reason is required exactly when ``assumed`` is
  true.
* Lenient normalization helpers (:func:`ensure_explicit_node`,
  :func:`annotate_graph`) for provider output, which fill in a generic
  default reason instead of failing the pipeline.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bizora.contracts.evidence import Provenance
from bizora.contracts.graph import GraphEdge, GraphNode, MethodologyGraph

#: Config key carrying the boolean assumed flag.
ASSUMED_CONFIG_KEY = "assumed"

#: Config key carrying the human-readable assumption reason.
ASSUMPTION_REASON_CONFIG_KEY = "assumption_reason"

#: Generic fallback reason. It names no domain, paper, or part.
DEFAULT_ASSUMPTION_REASON = "Not stated in the source; confirm or correct this claim."

#: Maximum stored reason length; longer provider-supplied reasons are truncated.
MAX_ASSUMPTION_REASON_LENGTH = 2000

_NODE_ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$"


def _validate_flag(reason_required: bool, reason: str | None, owner: str) -> None:
    """Enforce the strict contract: a reason exists exactly when assumed."""
    if reason_required and (reason is None or not reason.strip()):
        raise ValueError(f"{owner}: a reason is required when assumed is true")
    if not reason_required and reason is not None:
        raise ValueError(f"{owner}: reason must be null when assumed is false")


class AssumptionFlag(BaseModel):
    """One explicit assumed marking with its grounding reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assumed: bool
    reason: str | None = Field(default=None, max_length=MAX_ASSUMPTION_REASON_LENGTH)

    @model_validator(mode="after")
    def validate_reason_present_iff_assumed(self) -> "AssumptionFlag":
        _validate_flag(self.assumed, self.reason, "assumption flag")
        return self


class AssumedComponent(BaseModel):
    """Assumed marking for one extracted graph component (node)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=_NODE_ID_PATTERN)
    assumed: bool
    reason: str | None = Field(default=None, max_length=MAX_ASSUMPTION_REASON_LENGTH)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_reason_present_iff_assumed(self) -> "AssumedComponent":
        _validate_flag(self.assumed, self.reason, f"component '{self.node_id}'")
        return self


class AssumedPart(BaseModel):
    """Assumed marking for one part mention outside the graph.

    ``reference`` is the free-text mention as seen by extraction (a part
    number, a package, or a description); it is data, never a
    hard-coded vocabulary entry.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(min_length=1, max_length=2000)
    part_number: str | None = Field(default=None, max_length=128)
    assumed: bool
    reason: str | None = Field(default=None, max_length=MAX_ASSUMPTION_REASON_LENGTH)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_reason_present_iff_assumed(self) -> "AssumedPart":
        _validate_flag(self.assumed, self.reason, "part marking")
        return self


class AssumptionSummary(BaseModel):
    """Coverage counts for one graph revision (R2 acceptance helper)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_nodes: int = Field(ge=0)
    assumed_nodes: int = Field(ge=0)
    evidenced_nodes: int = Field(ge=0)
    unmarked_nodes: int = Field(ge=0)

    @property
    def complete(self) -> bool:
        """True when every node has evidence or an explicit assumed flag."""
        return self.unmarked_nodes == 0


def is_assumed(config: Mapping[str, Any]) -> bool:
    """Return True only when the mapping carries an explicit true flag."""
    return config.get(ASSUMED_CONFIG_KEY) is True


def assumption_reason(config: Mapping[str, Any]) -> str | None:
    """Return the stored reason, or None when absent or blank."""
    reason = config.get(ASSUMPTION_REASON_CONFIG_KEY)
    if not isinstance(reason, str) or not reason.strip():
        return None
    return reason


def assumption_config(reason: str) -> dict[str, Any]:
    """Build the config entries that visibly mark a claim as assumed."""
    return {
        ASSUMED_CONFIG_KEY: True,
        ASSUMPTION_REASON_CONFIG_KEY: _clean_reason(reason),
    }


def strip_assumption(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of the mapping with assumed marking removed."""
    return {
        key: value
        for key, value in config.items()
        if key not in (ASSUMED_CONFIG_KEY, ASSUMPTION_REASON_CONFIG_KEY)
    }


def node_is_assumed(node: GraphNode) -> bool:
    """Return True when the node carries an explicit assumed flag."""
    return is_assumed(node.config)


def node_assumption_reason(node: GraphNode) -> str | None:
    """Return the node's stored assumption reason, if any."""
    return assumption_reason(node.config)


def edge_is_assumed(edge: GraphEdge) -> bool:
    """Return True when an edge is visibly marked as assumed.

    Edges have no config mapping, so the marking is ``INFERRED``
    provenance with no evidence.
    """
    return not edge.evidence and edge.provenance == Provenance.INFERRED


def _clean_reason(reason: str | None) -> str:
    """Normalize a provider-supplied reason without ever failing."""
    if reason is None or not reason.strip():
        return DEFAULT_ASSUMPTION_REASON
    cleaned = reason.strip()
    if len(cleaned) > MAX_ASSUMPTION_REASON_LENGTH:
        cleaned = cleaned[: MAX_ASSUMPTION_REASON_LENGTH - 1].rstrip() + "…"
    return cleaned


def mark_assumed(
    node: GraphNode,
    reason: str,
    *,
    confidence: float | None = None,
) -> GraphNode:
    """Return a copy of the node visibly marked as assumed.

    Provenance moves to ``INFERRED`` only from ``UNRESOLVED``; any
    stronger provider-supplied provenance is preserved.
    """
    config = dict(node.config)
    config.update(assumption_config(reason))
    provenance = node.provenance
    if provenance == Provenance.UNRESOLVED:
        provenance = Provenance.INFERRED
    return node.model_copy(
        update={
            "config": config,
            "provenance": provenance,
            "confidence": confidence if confidence is not None else node.confidence,
        }
    )


def clear_assumed(
    node: GraphNode,
    *,
    provenance: Provenance = Provenance.VERIFIED,
) -> GraphNode:
    """Return a copy of the node with assumed marking removed."""
    return node.model_copy(
        update={"config": strip_assumption(node.config), "provenance": provenance}
    )


def ensure_explicit_node(
    node: GraphNode,
    *,
    default_reason: str = DEFAULT_ASSUMPTION_REASON,
) -> GraphNode:
    """Ensure the node has evidence or an explicit assumed flag.

    Nodes already carrying either are returned unchanged (idempotent);
    anything else is marked assumed with the default reason so the R2
    invariant holds: 100% of nodes have evidence or an explicit flag.
    """
    if node.evidence and not node_is_assumed(node):
        return node
    if node_is_assumed(node):
        reason = node_assumption_reason(node)
        if reason is not None:
            if node.provenance == Provenance.UNRESOLVED:
                return node.model_copy(update={"provenance": Provenance.INFERRED})
            return node
        return mark_assumed(node, _clean_reason(default_reason), confidence=node.confidence)
    return mark_assumed(node, _clean_reason(default_reason))


def ensure_explicit_edge(edge: GraphEdge) -> GraphEdge:
    """Ensure an evidence-less unresolved edge is visibly marked assumed."""
    if not edge.evidence and edge.provenance == Provenance.UNRESOLVED:
        return edge.model_copy(update={"provenance": Provenance.INFERRED})
    return edge


def annotate_graph(
    graph: MethodologyGraph,
    *,
    default_reason: str = DEFAULT_ASSUMPTION_REASON,
) -> MethodologyGraph:
    """Return a copy of the graph with every claim explicitly marked.

    Idempotent: re-annotating an annotated graph returns an equal graph.
    Identity fields (project, graph, version, lineage) are preserved.
    """
    nodes = tuple(ensure_explicit_node(node, default_reason=default_reason) for node in graph.nodes)
    edges = tuple(ensure_explicit_edge(edge) for edge in graph.edges)
    return graph.model_copy(update={"nodes": nodes, "edges": edges})


def summarize_assumptions(graph: MethodologyGraph) -> AssumptionSummary:
    """Count evidence/assumed coverage for one graph revision."""
    assumed = sum(1 for node in graph.nodes if node_is_assumed(node))
    evidenced = sum(1 for node in graph.nodes if node.evidence)
    unmarked = sum(1 for node in graph.nodes if not node.evidence and not node_is_assumed(node))
    return AssumptionSummary(
        total_nodes=len(graph.nodes),
        assumed_nodes=assumed,
        evidenced_nodes=evidenced,
        unmarked_nodes=unmarked,
    )
