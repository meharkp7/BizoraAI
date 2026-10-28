"""Tests for the Modal-backed isolation provider and executor.

No live Modal calls: submission tests prove the fail-closed paths
(missing SDK, missing credentials) and never reach the network.
"""

import importlib.util
from typing import Any

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from bizora.adapters.isolation import (
    IsolationProvider,
    IsolationRequirement,
    LocalIsolationProvider,
)
from bizora.adapters.modal_executor import (
    MAX_MEMORY_MB,
    MIN_MEMORY_MB,
    ModalExecutor,
    ModalFunctionSpec,
    ModalIsolationProvider,
    ModalUnavailableError,
    build_modal_spec,
)
from bizora.contracts.execution import (
    AdapterExecutionRequest,
    ExecutionLimits,
)
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import (
    GraphEdge,
    GraphNode,
    MethodologyGraph,
    NodeKind,
)
from bizora.core.errors import ErrorCode

FAKE_TOKEN_ID = "FAKE-MODAL-TOKEN-ID"
FAKE_TOKEN_SECRET = "FAKE-MODAL-TOKEN-SECRET"


def make_config(**overrides: Any) -> ExperimentConfig:
    """Build a minimal run config for spec tests."""
    payload: dict[str, Any] = {
        "experiment_id": "exp-1",
        "project_id": "project-1",
        "graph_id": "graph-1",
        "graph_version": 1,
        "adapter_id": "bizora.deterministic-test",
        "adapter_version": "0.1.0",
        "dataset_id": "dataset-1",
        "dataset_revision": "rev-1",
        "seed": 7,
        "epochs": 1,
        "batch_size": 8,
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
        title="Spec test graph",
        source_ids=("paper-1",),
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, label="Image"),
            GraphNode(id="output", kind=NodeKind.OUTPUT, label="Predictions"),
        ),
        edges=(GraphEdge(id="edge-1", source="input", target="output"),),
        created_by="researcher-1",
    )


def make_request(
    config: ExperimentConfig | None = None,
    limits: ExecutionLimits | None = None,
) -> AdapterExecutionRequest:
    """Build one adapter execution request."""
    return AdapterExecutionRequest(
        run_id="run-1",
        config=config or make_config(),
        graph=make_graph(),
        limits=limits
        or ExecutionLimits(
            timeout_seconds=1800,
            cpu_seconds=1800,
            soft_rss_mb=4096,
            max_output_bytes=1_000_000,
            kill_grace_seconds=5,
        ),
    )


def test_modal_provider_satisfies_isolation_protocol() -> None:
    provider = ModalIsolationProvider()

    assert isinstance(provider, IsolationProvider)
    assert provider.provider_id == "bizora.modal"
    assert provider.supports(IsolationRequirement.ISOLATED)
    assert provider.supports(IsolationRequirement.LOCAL_TRUSTED)


def test_local_provider_still_fails_closed_for_isolated() -> None:
    assert not LocalIsolationProvider().supports(IsolationRequirement.ISOLATED)


def test_spec_defaults_are_fail_closed() -> None:
    spec = build_modal_spec(make_request())

    assert spec.network_enabled is False
    assert spec.allowed_hosts == ()
    assert spec.workspace == "/workspace"
    assert spec.timeout_seconds == 1800
    assert spec.memory_mb == 4096
    assert spec.gpu_count == 0
    assert "env" not in spec.model_dump()


def test_spec_caps_timeout_and_clamps_memory() -> None:
    huge = make_request(
        limits=ExecutionLimits(
            timeout_seconds=86_400,
            cpu_seconds=86_400,
            soft_rss_mb=1_000_000,
            max_output_bytes=1_000_000,
            kill_grace_seconds=5,
        )
    )
    spec = build_modal_spec(huge, max_timeout_seconds=600)

    assert spec.timeout_seconds == 600
    assert spec.memory_mb == MAX_MEMORY_MB

    tiny = make_request(
        limits=ExecutionLimits(
            timeout_seconds=60,
            cpu_seconds=60,
            soft_rss_mb=1,
            max_output_bytes=1_000_000,
            kill_grace_seconds=0,
        )
    )
    small = build_modal_spec(tiny, default_memory_mb=64)

    assert small.timeout_seconds == 60
    assert small.memory_mb == MIN_MEMORY_MB


def test_spec_mirrors_explicit_network_access() -> None:
    networked = build_modal_spec(make_request(make_config(network_access=True)))

    assert networked.network_enabled is True

    with pytest.raises(ValidationError):
        ModalFunctionSpec(
            app_name="app",
            function_name="fn",
            adapter_id="a",
            adapter_version="1",
            timeout_seconds=60,
            memory_mb=512,
            gpu_count=0,
            network_enabled=False,
            allowed_hosts=("example.test",),
        )


def test_spec_rejects_bad_executor_bounds() -> None:
    with pytest.raises(ValueError):
        build_modal_spec(make_request(), max_timeout_seconds=0)
    with pytest.raises(ValueError):
        ModalExecutor(max_timeout_seconds=100_000)


def test_credentials_check_is_presence_only(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    assert ModalExecutor.credentials_present() is False

    monkeypatch.setenv("MODAL_TOKEN_ID", FAKE_TOKEN_ID)
    assert ModalExecutor.credentials_present() is False

    monkeypatch.setenv("MODAL_TOKEN_SECRET", FAKE_TOKEN_SECRET)
    assert ModalExecutor.credentials_present() is True


def test_sdk_availability_matches_import_system() -> None:
    assert ModalExecutor.sdk_available() == (
        importlib.util.find_spec("modal") is not None
    )


def test_submit_fails_closed_without_sdk(monkeypatch: MonkeyPatch) -> None:
    if ModalExecutor.sdk_available():
        pytest.skip("Modal SDK installed; live-capable environment.")
    monkeypatch.setenv("MODAL_TOKEN_ID", FAKE_TOKEN_ID)
    monkeypatch.setenv("MODAL_TOKEN_SECRET", FAKE_TOKEN_SECRET)

    def explode(spec: ModalFunctionSpec, payload: str) -> str:
        raise AssertionError("fail-closed submit must never invoke Modal")

    monkeypatch.setattr(ModalExecutor, "_invoke", explode)

    with pytest.raises(ModalUnavailableError) as exc_info:
        ModalExecutor().submit(make_request())

    assert exc_info.value.code == ErrorCode.PROVIDER_UNAVAILABLE
    assert FAKE_TOKEN_ID not in str(exc_info.value)
    assert FAKE_TOKEN_SECRET not in str(exc_info.value)


def test_submit_fails_closed_without_credentials(monkeypatch: MonkeyPatch) -> None:
    if ModalExecutor.sdk_available():
        pytest.skip("Modal SDK installed; live-capable environment.")
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)

    with pytest.raises(ModalUnavailableError) as exc_info:
        ModalExecutor().submit(make_request())

    assert exc_info.value.code == ErrorCode.PROVIDER_UNAVAILABLE
