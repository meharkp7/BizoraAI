"""Tests for the execution adapter registry."""

import pytest

from bizora.adapters.base import ExecutionAdapter
from bizora.adapters.deterministic_test import DeterministicTestAdapter
from bizora.adapters.isolation import IsolationRequirement
from bizora.adapters.registry import AdapterRegistry, create_default_registry
from bizora.contracts.execution import AdapterExecutionRequest, ExecutionResult
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import MethodologyGraph
from bizora.core.errors import BizoraError, ErrorCode


class StubAdapter:
    """Minimal adapter for registry behavior tests."""

    def __init__(self, adapter_id: str, adapter_version: str) -> None:
        self._adapter_id = adapter_id
        self._adapter_version = adapter_version

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    @property
    def isolation_requirement(self) -> IsolationRequirement:
        return IsolationRequirement.ISOLATED

    def check_compatibility(
        self,
        config: ExperimentConfig,
        graph: MethodologyGraph,
    ) -> tuple[str, ...]:
        del config, graph
        return ()

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        raise NotImplementedError


def test_stub_satisfies_adapter_protocol() -> None:
    assert isinstance(StubAdapter("stub", "0.1.0"), ExecutionAdapter)
    assert isinstance(DeterministicTestAdapter(), ExecutionAdapter)


def test_default_registry_resolves_test_adapter() -> None:
    registry = create_default_registry()

    adapter = registry.resolve("bizora.deterministic-test", "0.1.0")

    assert isinstance(adapter, DeterministicTestAdapter)
    assert registry.available() == (("bizora.deterministic-test", "0.1.0"),)


def test_resolve_rejects_unknown_adapter_id() -> None:
    registry = create_default_registry()

    with pytest.raises(BizoraError) as exc_info:
        registry.resolve("bizora.unknown", "0.1.0")

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST
    assert exc_info.value.details["adapter_id"] == "bizora.unknown"
    assert exc_info.value.details["available"] == [
        {"adapter_id": "bizora.deterministic-test", "adapter_version": "0.1.0"}
    ]


def test_resolve_rejects_wrong_adapter_version() -> None:
    registry = create_default_registry()

    with pytest.raises(BizoraError) as exc_info:
        registry.resolve("bizora.deterministic-test", "9.9.9")

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST
    assert "9.9.9" in str(exc_info.value)


def test_register_rejects_duplicates() -> None:
    registry = AdapterRegistry([DeterministicTestAdapter()])

    with pytest.raises(ValueError, match="already registered"):
        registry.register(DeterministicTestAdapter())


def test_registries_are_independent() -> None:
    first = AdapterRegistry([StubAdapter("stub-a", "1.0.0")])
    second = AdapterRegistry([StubAdapter("stub-b", "1.0.0")])

    assert first.available() == (("stub-a", "1.0.0"),)
    assert second.available() == (("stub-b", "1.0.0"),)

    with pytest.raises(BizoraError):
        first.resolve("stub-b", "1.0.0")
