"""Tests for the ngspice execution adapter.

Simulation tests run a REAL local ngspice binary in batch mode (no
fakes for the simulation itself). They skip only when no binary is
available; on this machine /opt/homebrew/bin/ngspice exists.
"""

import pytest

from bizora.adapters.base import ExecutionAdapter
from bizora.adapters.ngspice_adapter import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    NgspiceAdapter,
)
from bizora.adapters.ngspice_runner import (
    parse_failed_measurements,
    parse_measurements,
    resolve_ngspice,
)
from bizora.adapters.registry import AdapterRegistry
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionStatus,
)
from bizora.contracts.experiment import ExperimentConfig, ResultKind
from bizora.contracts.graph import (
    GraphNode,
    MethodologyGraph,
    NodeKind,
)

NGSPICE = resolve_ngspice()
needs_ngspice = pytest.mark.skipif(NGSPICE is None, reason="no ngspice binary available")


def make_node(node_id: str, label: str, **config: object) -> GraphNode:
    """Build one component node with the given config data."""
    return GraphNode(id=node_id, kind=NodeKind.COMPONENT, label=label, config=dict(config))


def divider_nodes(r2_value: str = "1k") -> tuple[GraphNode, ...]:
    """Build a divider with an operating-point readout of v(out)."""
    directives = (".op", ".control", "run", "print v(out)", ".endc")
    return (
        make_node(
            "v1",
            "Supply",
            spice_kind="voltage-source",
            refdes="V1",
            nets=["in", "0"],
            voltage_v="5",
        ),
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["in", "out"],
            resistance_ohm="1k",
        ),
        make_node(
            "r2",
            "Resistor",
            spice_kind="resistor",
            refdes="R2",
            nets=["out", "0"],
            resistance_ohm=r2_value,
        ),
        *(
            make_node(f"d{index}", "Directive", spice_kind="directive", line=text)
            for index, text in enumerate(directives)
        ),
    )


def make_graph(nodes: tuple[GraphNode, ...]) -> MethodologyGraph:
    """Build a methodology graph from component nodes."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        title="Divider",
        nodes=nodes,
        created_by="tester",
    )


def make_config(**overrides: object) -> ExperimentConfig:
    """Build a config targeting the ngspice adapter."""
    payload: dict[str, object] = {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "dataset_id": "divider",
        "dataset_revision": "rev-1",
        "seed": 7,
        "epochs": 1,
        "batch_size": 1,
        "learning_rate": 0.001,
        "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "code_revision": "abcdef1",
        "max_runtime_seconds": 300,
        "max_gpu_count": 0,
    }
    payload.update(overrides)
    return ExperimentConfig.model_validate(payload)


def make_request(graph: MethodologyGraph, config: ExperimentConfig) -> AdapterExecutionRequest:
    """Build an execution request for the ngspice adapter."""
    return AdapterExecutionRequest(
        run_id="run-1",
        config=config,
        graph=graph,
        limits=ExecutionLimits(
            timeout_seconds=120,
            cpu_seconds=120,
            soft_rss_mb=512,
            max_output_bytes=1_000_000,
            kill_grace_seconds=5,
        ),
    )


def metric_value(result: object, metric_id: str) -> float:
    """Return one metric value by id from an execution result."""
    assert hasattr(result, "metrics")
    metrics = result.metrics
    for metric in metrics:
        if metric.metric_id == metric_id:
            return float(metric.value)
    raise AssertionError(f"metric '{metric_id}' missing")


def test_adapter_implements_the_shared_interface() -> None:
    """The adapter satisfies the ExecutionAdapter protocol exactly."""
    adapter = NgspiceAdapter()

    assert isinstance(adapter, ExecutionAdapter)
    assert adapter.adapter_id == "bizora.ngspice"
    assert adapter.adapter_version == "0.1.0"


def test_adapter_resolves_through_registry() -> None:
    """The adapter registers and resolves by exact id and version."""
    registry = AdapterRegistry([NgspiceAdapter()])

    resolved = registry.resolve(ADAPTER_ID, ADAPTER_VERSION)

    assert isinstance(resolved, NgspiceAdapter)


def test_compatibility_rejects_mismatches() -> None:
    """Wrong id, network access, and empty graphs are refused."""
    adapter = NgspiceAdapter()
    graph = make_graph(divider_nodes())

    assert any(
        "does not match" in reason
        for reason in adapter.check_compatibility(make_config(adapter_id="bizora.other"), graph)
    )
    assert any(
        "network" in reason
        for reason in adapter.check_compatibility(make_config(network_access=True), graph)
    )
    assert any(
        "spice_kind" in reason
        for reason in adapter.check_compatibility(
            make_config(), make_graph((make_node("n", "Plain"),))
        )
    )
    if NGSPICE is not None:
        assert adapter.check_compatibility(make_config(), graph) == ()


def test_execute_rejects_without_raising() -> None:
    """Incompatible runs fail with a structured error, never a raise."""
    adapter = NgspiceAdapter()
    request = make_request(make_graph((make_node("n", "Plain"),)), make_config())

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.ADAPTER_INCOMPATIBLE


@needs_ngspice
def test_execute_measures_divider_output() -> None:
    """A real ngspice run measures v(out) = 2.5 V on a 1k/1k divider."""
    adapter = NgspiceAdapter()
    request = make_request(make_graph(divider_nodes("1k")), make_config())

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert metric_value(result, "v(out)") == pytest.approx(2.5, abs=1e-6)
    kinds = {metric.result_kind for metric in result.metrics}
    assert kinds == {ResultKind.MEASURED}
    assert result.echo.adapter_id == ADAPTER_ID
    assert result.echo.graph_version == 1


@needs_ngspice
def test_edit_changes_measured_output() -> None:
    """Editing R2 from 1k to 3k moves the measured v(out) 2.5 V -> 3.75 V."""
    adapter = NgspiceAdapter()
    before = adapter.execute(make_request(make_graph(divider_nodes("1k")), make_config()))
    after = adapter.execute(make_request(make_graph(divider_nodes("3k")), make_config()))

    assert before.status is ExecutionStatus.SUCCEEDED
    assert after.status is ExecutionStatus.SUCCEEDED
    v_before = metric_value(before, "v(out)")
    v_after = metric_value(after, "v(out)")
    assert v_before == pytest.approx(2.5, abs=1e-6)
    assert v_after == pytest.approx(3.75, abs=1e-6)
    assert abs(v_after - v_before) > 0.5


@needs_ngspice
def test_execute_reports_tran_meas_metrics() -> None:
    """A .meas tran directive flows through as a measured metric."""
    adapter = NgspiceAdapter()
    directives = (
        ".tran 10n 20u",
        ".meas tran vmax MAX v(out)",
        ".control",
        "run",
        ".endc",
    )
    nodes = (
        make_node(
            "v1",
            "Supply",
            spice_kind="voltage-source",
            refdes="V1",
            nets=["in", "0"],
            voltage_v="5",
            spice_args="PULSE(0 5 0 1n 1n 5u 10u)",
        ),
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["in", "out"],
            resistance_ohm="1k",
        ),
        make_node(
            "c1",
            "Capacitor",
            spice_kind="capacitor",
            refdes="C1",
            nets=["out", "0"],
            capacitance_f="1n",
        ),
        *(
            make_node(f"d{index}", "Directive", spice_kind="directive", line=text)
            for index, text in enumerate(directives)
        ),
    )
    result = adapter.execute(make_request(make_graph(nodes), make_config()))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert metric_value(result, "vmax") == pytest.approx(4.97, abs=0.05)


@needs_ngspice
def test_execute_fails_cleanly_without_measurements() -> None:
    """A run with no print/.meas directives fails with guidance."""
    adapter = NgspiceAdapter()
    nodes = (
        make_node(
            "v1",
            "Supply",
            spice_kind="voltage-source",
            refdes="V1",
            nets=["in", "0"],
            voltage_v="5",
        ),
        make_node(
            "r1",
            "Resistor",
            spice_kind="resistor",
            refdes="R1",
            nets=["in", "0"],
            resistance_ohm="1k",
        ),
        make_node("d0", "Directive", spice_kind="directive", line=".op"),
    )
    result = adapter.execute(make_request(make_graph(nodes), make_config()))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code is ExecutionErrorCode.ADAPTER_FAILED
    assert "print or .meas" in result.error.message


def test_parse_measurements_keeps_first_per_name() -> None:
    """Repeated analysis passes do not duplicate metric names."""
    output = "vmid                =  3.33333e+00\nvmid                =  3.33333e+00\n"

    assert parse_measurements(output) == (parse_measurements("vmid = 3.33333e+00")[0],)


def test_parse_measurements_ignores_tables() -> None:
    """Op tables and timing lines without '=' never become metrics."""
    output = (
        "out                              2.500000e+00\n"
        "Total analysis time (seconds) = 0.000542\n"
        "v(out) = 2.500000e+00\n"
    )

    parsed = parse_measurements(output)

    assert [item.name for item in parsed] == ["v(out)"]


def test_parse_failed_measurements() -> None:
    """Measurements ngspice reports as failed are collected by name."""
    output = "vmax = failed\nvmin = 1.000000e+00\n"

    assert parse_failed_measurements(output) == ("vmax",)
    assert [item.name for item in parse_measurements(output)] == ["vmin"]
