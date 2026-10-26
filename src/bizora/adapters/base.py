"""Provider-neutral interface for experiment execution adapters."""

from typing import Protocol, runtime_checkable

from bizora.contracts.execution import AdapterExecutionRequest, ExecutionResult
from bizora.contracts.experiment import ExperimentConfig
from bizora.contracts.graph import MethodologyGraph


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Interface implemented by every registered execution adapter."""

    @property
    def adapter_id(self) -> str:
        """Return the stable adapter identifier."""
        ...

    @property
    def adapter_version(self) -> str:
        """Return the exact adapter version."""
        ...

    def check_compatibility(
        self,
        config: ExperimentConfig,
        graph: MethodologyGraph,
    ) -> tuple[str, ...]:
        """Return incompatibility reasons; empty means the adapter accepts the run."""
        ...

    def execute(self, request: AdapterExecutionRequest) -> ExecutionResult:
        """Execute one run and return its outcome without raising for domain failures."""
        ...
