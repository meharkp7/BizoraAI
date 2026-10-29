"""Versioned methodology graph contracts and invariant checks."""

from collections import defaultdict, deque
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bizora.contracts.evidence import EvidenceRef, Provenance


class NodeKind(StrEnum):
    INPUT = "input"
    PREPROCESSING = "preprocessing"
    MODEL = "model"
    OPERATION = "operation"
    LOSS = "loss"
    OPTIMIZER = "optimizer"
    EVALUATION = "evaluation"
    OUTPUT = "output"
    DATASET = "dataset"
    COMPONENT = "component"


#: Node kinds that are processes or data by definition, never hardware.
#: Resolution routes these to process entities without text matching,
#: so a dataset can never resolve to a physical instrument no matter
#: which measurement words its description carries. Ambiguous kinds
#: (input, output, model, component) still resolve by text: a supply
#: input is hardware while an image input is data.
NON_PHYSICAL_NODE_KINDS = frozenset(
    {
        NodeKind.PREPROCESSING.value,
        NodeKind.OPERATION.value,
        NodeKind.LOSS.value,
        NodeKind.OPTIMIZER.value,
        NodeKind.EVALUATION.value,
        NodeKind.DATASET.value,
    }
)


class RelationKind(StrEnum):
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    OPTIMIZES = "optimizes"
    EVALUATES = "evaluates"
    DEPENDS_ON = "depends_on"


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
    kind: NodeKind
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)
    input_shape: tuple[int | None, ...] | None = None
    output_shape: tuple[int | None, ...] | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance = Provenance.UNRESOLVED
    confidence: float | None = Field(default=None, ge=0, le=1)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    relation: RelationKind = RelationKind.DATA_FLOW
    label: str | None = Field(default=None, max_length=200)
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance = Provenance.UNRESOLVED


class ResearchBrief(BaseModel):
    """Paper-level context: what was studied and what was found.

    Every field is optional: absent information stays null or empty and
    must never be fabricated by extraction providers.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    problem: str | None = Field(default=None, max_length=2000)
    objectives: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class MethodologyGraph(BaseModel):
    """One immutable graph revision; mutations must create a new version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    project_id: str = Field(min_length=1, max_length=128)
    graph_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    source_ids: tuple[str, ...] = ()
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...] = ()
    created_by: str = Field(min_length=1, max_length=128)
    parent_version: int | None = Field(default=None, ge=1)
    brief: ResearchBrief | None = None

    @model_validator(mode="after")
    def validate_version_lineage(self) -> "MethodologyGraph":
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ValueError("parent_version must be lower than version")
        return self


def validate_graph(graph: MethodologyGraph, *, require_dag: bool = False) -> list[str]:
    """Return all graph invariant violations; empty list means structurally valid.

    Cycles are legitimate in feedback systems, recurrent architectures, and
    circuits, so graphs are cyclic-tolerant by default. Pass require_dag=True
    only for callers that explicitly need the feed-forward profile.
    """
    errors: list[str] = []
    node_ids = [node.id for node in graph.nodes]
    edge_ids = [edge.id for edge in graph.edges]
    if len(node_ids) != len(set(node_ids)):
        errors.append("node IDs must be unique")
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("edge IDs must be unique")

    known_nodes = set(node_ids)
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in known_nodes}
    for edge in graph.edges:
        if edge.source not in known_nodes:
            errors.append(f"edge '{edge.id}' references missing source node '{edge.source}'")
        if edge.target not in known_nodes:
            errors.append(f"edge '{edge.id}' references missing target node '{edge.target}'")
        if edge.source == edge.target:
            errors.append(f"edge '{edge.id}' cannot connect a node to itself")
        if edge.source in known_nodes and edge.target in known_nodes and edge.source != edge.target:
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1

    declared_sources = set(graph.source_ids)
    for node in graph.nodes:
        for evidence in node.evidence:
            if evidence.source_id not in declared_sources:
                errors.append(
                    f"node '{node.id}' evidence references undeclared source '{evidence.source_id}'"
                )
    for edge in graph.edges:
        for evidence in edge.evidence:
            if evidence.source_id not in declared_sources:
                errors.append(
                    f"edge '{edge.id}' evidence references undeclared source '{evidence.source_id}'"
                )

    if require_dag and known_nodes:
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in adjacency[current]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)
        if visited != len(known_nodes):
            errors.append("graph contains a cycle; feed-forward graph profile requires a DAG")
    return errors
