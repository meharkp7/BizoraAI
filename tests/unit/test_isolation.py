"""Tests for the execution isolation boundary.

Local subprocess supervision is not a security sandbox: it may only run
adapters explicitly declared as local-trusted, and it must fail closed
for anything requiring stronger isolation.
"""

import json
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from bizora.adapters.base import ExecutionAdapter
from bizora.adapters.deterministic_test import DeterministicTestAdapter
from bizora.adapters.isolation import (
    IsolationProvider,
    IsolationRequirement,
    LocalIsolationProvider,
    requirement_of,
)
from bizora.adapters.registry import AdapterRegistry
from bizora.adapters.runner import run_adapter
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionErrorCode,
    ExecutionLimits,
    ExecutionResult,
    StructuredError,
)
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.contracts.run import ExperimentRun, RunState
from bizora.core.execution_service import ExecutionService, WorkerConfig
from bizora.db.base import Base
from bizora.db.repository import save_experiment_run, save_graph_revision

FIXTURE = Path(__file__).parent.parent / "fixtures" / "fake_adapter_child.py"


class IsolatedStubAdapter:
    """Adapter that requires a real isolation backend."""

    adapter_id = "stub.isolated"
    adapter_version = "9.9.9"
    isolation_requirement = IsolationRequirement.ISOLATED

    def check_compatibility(
        self, config: ExperimentConfig, graph: MethodologyGraph
    ) -> tuple[str, ...]:
        del config, graph
        return ()

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        raise AssertionError("isolated adapter must never execute locally")


class NetworkedLocalStubAdapter:
    """Local-trusted adapter that wrongly permits network access."""

    adapter_id = "stub.networked-local"
    adapter_version = "1.0.0"
    isolation_requirement = IsolationRequirement.LOCAL_TRUSTED

    def check_compatibility(
        self, config: ExperimentConfig, graph: MethodologyGraph
    ) -> tuple[str, ...]:
        del config, graph
        return ()

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        raise AssertionError("must not execute")


class AllowAllIsolationProvider:
    """Test-only provider standing in for a future isolated backend."""

    provider_id = "test.allow-all"

    def supports(self, requirement: IsolationRequirement) -> bool:
        del requirement
        return True


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Create an isolated file database for each test."""
    engine = create_engine(f"sqlite:///{tmp_path}/isolation.db", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a factory for short-lived sessions."""
    return lambda: Session(engine)


def make_config(**overrides: Any) -> ExperimentConfig:
    """Build a config, retargetable at stub adapters."""
    payload: dict[str, Any] = {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "bizora.deterministic-test",
        "adapter_version": "0.1.0",
        "dataset_id": "cifar10-subset",
        "dataset_revision": "sha256:example",
        "seed": 42,
        "epochs": 3,
        "batch_size": 32,
        "learning_rate": 0.001,
        "split": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "code_revision": "abcdef1",
        "max_runtime_seconds": 1800,
        "max_gpu_count": 0,
    }
    payload.update(overrides)
    return ExperimentConfig.model_validate(payload)


def make_graph() -> MethodologyGraph:
    """Build a minimal methodology graph."""
    return MethodologyGraph(
        project_id="project-1",
        graph_id="graph-1",
        version=1,
        parent_version=None,
        title="Vision Transformer",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(GraphEdge(id="edge-1", source="input", target="output"),),
        created_by="researcher-1",
    )


def seed_run(
    session_factory: Callable[[], Session],
    run_id: str,
    config: ExperimentConfig,
) -> None:
    """Persist the graph revision and one pending run."""
    session = session_factory()
    try:
        save_graph_revision(session, make_graph())
        save_experiment_run(
            session,
            ExperimentRun(
                run_id=run_id,
                config=config,
                state=RunState.PENDING,
                created_at=datetime.now(UTC),
            ),
        )
        session.commit()
    finally:
        session.close()


def error_code_of(error_value: str | None) -> str | None:
    """Return the structured error code from a run error value."""
    if error_value is None:
        return None
    return str(json.loads(error_value)["code"])


def test_undeclared_adapter_fails_closed_to_isolated() -> None:
    assert requirement_of(object()) == IsolationRequirement.ISOLATED


def test_garbage_tier_declaration_fails_closed() -> None:
    class WeirdAdapter:
        isolation_requirement = "local_trusted"

    assert requirement_of(WeirdAdapter()) == IsolationRequirement.ISOLATED


def test_deterministic_adapter_is_local_trusted() -> None:
    adapter = DeterministicTestAdapter()

    assert isinstance(adapter, ExecutionAdapter)
    assert requirement_of(adapter) == IsolationRequirement.LOCAL_TRUSTED


def test_local_provider_supports_only_local_trusted() -> None:
    provider = LocalIsolationProvider()

    assert isinstance(provider, IsolationProvider)
    assert provider.supports(IsolationRequirement.LOCAL_TRUSTED)
    assert not provider.supports(IsolationRequirement.ISOLATED)


def test_isolation_unavailable_error_round_trips() -> None:
    error = StructuredError(
        code=ExecutionErrorCode.ISOLATION_UNAVAILABLE,
        message="Isolated backend required.",
    )

    assert json.loads(error.to_record_value())["code"] == "isolation_unavailable"


def test_execute_run_rejects_isolated_adapter(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(
        session_factory,
        "run-1",
        make_config(adapter_id="stub.isolated", adapter_version="9.9.9"),
    )

    def exploding_argv(request_path: str, result_path: str) -> list[str]:
        raise AssertionError("rejected run must never spawn a child")

    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        registry=AdapterRegistry([IsolatedStubAdapter()]),
        argv_factory=exploding_argv,
    )

    final = service.execute_run("run-1")

    assert final.state == RunState.FAILED
    assert error_code_of(final.error) == "isolation_unavailable"


def test_execute_run_rejects_network_access_locally(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(
        session_factory,
        "run-1",
        make_config(
            adapter_id="stub.networked-local",
            adapter_version="1.0.0",
            network_access=True,
        ),
    )
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        registry=AdapterRegistry([NetworkedLocalStubAdapter()]),
        argv_factory=lambda request, result: [
            sys.executable,
            str(FIXTURE),
            "ok",
            request,
            result,
        ],
    )

    final = service.execute_run("run-1")

    assert final.state == RunState.FAILED
    assert error_code_of(final.error) == "isolation_unavailable"


def test_custom_provider_can_satisfy_isolated_requirement(
    session_factory: Callable[[], Session],
) -> None:
    seed_run(
        session_factory,
        "run-1",
        make_config(adapter_id="stub.isolated", adapter_version="9.9.9"),
    )
    service = ExecutionService(
        session_factory,
        WorkerConfig(worker_id="worker-a", poll_seconds=0.05),
        registry=AdapterRegistry([IsolatedStubAdapter()]),
        argv_factory=lambda request, result: [
            sys.executable,
            str(FIXTURE),
            "ok",
            request,
            result,
        ],
        isolation_provider=AllowAllIsolationProvider(),
    )

    final = service.execute_run("run-1")

    assert final.state == RunState.SUCCEEDED


def test_runner_refuses_isolated_adapter(tmp_path: Path) -> None:
    request = AdapterExecutionRequest(
        run_id="run-1",
        config=make_config(adapter_id="stub.isolated", adapter_version="9.9.9"),
        graph=make_graph(),
        limits=ExecutionLimits(
            timeout_seconds=60,
            cpu_seconds=60,
            soft_rss_mb=4096,
            max_output_bytes=1_000_000,
            kill_grace_seconds=5,
        ),
    )
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    try:
        run_adapter(
            str(request_path),
            str(result_path),
            registry=AdapterRegistry([IsolatedStubAdapter()]),
        )
    except ValueError as exc:
        assert "isolated" in str(exc)
    else:
        raise AssertionError("runner must refuse isolated adapters")

    assert not result_path.exists()


def test_runner_refuses_network_access(tmp_path: Path) -> None:
    request = AdapterExecutionRequest(
        run_id="run-1",
        config=make_config(network_access=True),
        graph=make_graph(),
        limits=ExecutionLimits(
            timeout_seconds=60,
            cpu_seconds=60,
            soft_rss_mb=4096,
            max_output_bytes=1_000_000,
            kill_grace_seconds=5,
        ),
    )
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")

    try:
        run_adapter(str(request_path), str(result_path))
    except ValueError as exc:
        assert "isolated" in str(exc)
    else:
        raise AssertionError("runner must refuse network-capable runs")

    assert not result_path.exists()
