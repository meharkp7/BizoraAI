"""Shared in-memory fixtures for copilot tests and the offline eval.

The fixture graph describes a synthetic system with paper evidence
on two nodes and one edge; one node is deliberately unresolved so
tests can cover the assumed path. Runs cover one success with
metrics and one failure with an error message. Nothing here is
production logic: these builders exist so unit tests and
``tests/copilot_eval`` share one deterministic world.
"""

from datetime import UTC, datetime

from bizora.contracts.evidence import EvidenceRef, EvidenceStatus, Provenance
from bizora.contracts.experiment import DatasetSplit, ExperimentConfig, ResultKind
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
    RelationKind,
)
from bizora.contracts.run import ExperimentRun, MetricRecord, RunState
from bizora.copilot.tools import CopilotContext

EVAL_SOURCE_ID = "eval-paper-1"
EVAL_PROJECT_ID = "eval-project"
EVAL_GRAPH_ID = "eval-graph"


def make_eval_graph(*, version: int = 1) -> MethodologyGraph:
    """Build the synthetic fixture revision (version 1 by default)."""
    return MethodologyGraph(
        project_id=EVAL_PROJECT_ID,
        graph_id=EVAL_GRAPH_ID,
        version=version,
        title="Synthetic evaluation system",
        source_ids=(EVAL_SOURCE_ID,),
        nodes=(
            GraphNode(
                id="sensor",
                kind=NodeKind.COMPONENT,
                label="Sensor front-end",
                description="The sensing front-end block.",
                config={"sampling_rate_hz": 16000},
                evidence=(
                    EvidenceRef(
                        source_id=EVAL_SOURCE_ID,
                        page=2,
                        quote="the front-end samples at 16 kHz",
                        status=EvidenceStatus.SUPPORTED,
                    ),
                ),
                provenance=Provenance.EXTRACTED,
                confidence=0.9,
            ),
            GraphNode(
                id="filter",
                kind=NodeKind.OPERATION,
                label="Filter stage",
                description="The filtering block.",
                config={"corner_hz": 4000},
                evidence=(
                    EvidenceRef(
                        source_id=EVAL_SOURCE_ID,
                        page=3,
                        quote="a second-order section with a 4 kHz corner",
                        figure_label="Figure 2",
                        status=EvidenceStatus.SUPPORTED,
                    ),
                ),
                provenance=Provenance.EXTRACTED,
                confidence=0.85,
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                label="Result sink",
                provenance=Provenance.UNRESOLVED,
            ),
        ),
        edges=(
            GraphEdge(
                id="e1",
                source="sensor",
                target="filter",
                relation=RelationKind.DATA_FLOW,
                evidence=(
                    EvidenceRef(
                        source_id=EVAL_SOURCE_ID,
                        page=2,
                        quote="front-end feeds the filter",
                        status=EvidenceStatus.PARTIAL,
                    ),
                ),
                provenance=Provenance.EXTRACTED,
            ),
            GraphEdge(
                id="e2",
                source="filter",
                target="output",
                relation=RelationKind.DATA_FLOW,
            ),
        ),
        created_by="eval",
    )


def make_eval_graph_v2() -> MethodologyGraph:
    """Build revision 2: filter retuned and a monitor node added."""
    base = make_eval_graph(version=1)
    nodes = []
    for node in base.nodes:
        if node.id == "filter":
            nodes.append(node.model_copy(update={"config": {"corner_hz": 8000}}))
        else:
            nodes.append(node)
    nodes.append(
        GraphNode(
            id="monitor",
            kind=NodeKind.EVALUATION,
            label="Monitor tap",
            provenance=Provenance.INFERRED,
            confidence=0.4,
        )
    )
    edges = base.edges + (
        GraphEdge(
            id="e3",
            source="filter",
            target="monitor",
            relation=RelationKind.DATA_FLOW,
        ),
    )
    return base.model_copy(
        update={
            "version": 2,
            "parent_version": 1,
            "nodes": tuple(nodes),
            "edges": edges,
        }
    )


def _eval_config(graph_version: int) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="eval-experiment",
        project_id=EVAL_PROJECT_ID,
        graph_id=EVAL_GRAPH_ID,
        graph_version=graph_version,
        adapter_id="bizora.deterministic-test",
        adapter_version="1.0",
        dataset_id="eval-dataset",
        dataset_revision="rev-1",
        seed=7,
        epochs=2,
        batch_size=8,
        learning_rate=0.01,
        split=DatasetSplit(train=0.8, validation=0.1, test=0.1),
        code_revision="abcdef1",
        max_runtime_seconds=60,
        max_gpu_count=0,
    )


def make_eval_runs() -> tuple[ExperimentRun, ...]:
    """Build one succeeded and one failed fixture run."""
    created = datetime(2026, 1, 1, tzinfo=UTC)
    started = datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)
    return (
        ExperimentRun(
            run_id="run-eval-1",
            config=_eval_config(1),
            state=RunState.SUCCEEDED,
            created_at=created,
            started_at=started,
            finished_at=finished,
        ),
        ExperimentRun(
            run_id="run-eval-2",
            config=_eval_config(2),
            state=RunState.FAILED,
            created_at=created,
            started_at=started,
            finished_at=finished,
            error="diverged after 3 steps: loss exceeded threshold",
        ),
    )


def make_eval_metrics() -> dict[str, tuple[MetricRecord, ...]]:
    """Build fixture metrics keyed by run id."""
    return {
        "run-eval-1": (
            MetricRecord(
                metric_id="m-accuracy",
                run_id="run-eval-1",
                name="accuracy",
                value=0.91,
                result_kind=ResultKind.MEASURED,
            ),
            MetricRecord(
                metric_id="m-loss",
                run_id="run-eval-1",
                name="loss",
                value=0.23,
                result_kind=ResultKind.MEASURED,
            ),
        ),
        "run-eval-2": (
            MetricRecord(
                metric_id="m-loss-2",
                run_id="run-eval-2",
                name="loss",
                value=12.5,
                result_kind=ResultKind.MEASURED,
            ),
        ),
    }


def make_eval_context(*, version: int = 2) -> CopilotContext:
    """Build an in-memory context over the fixture world."""
    revisions = {1: make_eval_graph(version=1), 2: make_eval_graph_v2()}
    runs = {run.run_id: run for run in make_eval_runs()}
    metrics = make_eval_metrics()
    return CopilotContext(
        graph=revisions[version],
        selected_node_id="filter",
        load_revision=revisions.get,
        list_runs=lambda: [runs["run-eval-1"], runs["run-eval-2"]],
        get_run=runs.get,
        list_metrics=lambda run_id: list(metrics.get(run_id, ())),
    )
