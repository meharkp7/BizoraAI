"""Explicit registry of approved experiment execution adapters."""

from collections.abc import Iterable

from bizora.adapters.base import ExecutionAdapter
from bizora.core.errors import BizoraError, ErrorCode


class AdapterRegistry:
    """Resolve adapters only by exact identifier and version."""

    def __init__(self, adapters: Iterable[ExecutionAdapter] = ()) -> None:
        self._adapters: dict[tuple[str, str], ExecutionAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ExecutionAdapter) -> None:
        """Add an adapter; duplicate registrations are wiring bugs."""
        key = (adapter.adapter_id, adapter.adapter_version)
        if key in self._adapters:
            raise ValueError(
                f"Adapter '{adapter.adapter_id}' version "
                f"'{adapter.adapter_version}' is already registered."
            )
        self._adapters[key] = adapter

    def resolve(self, adapter_id: str, adapter_version: str) -> ExecutionAdapter:
        """Return the exact registered adapter or fail with an actionable error."""
        adapter = self._adapters.get((adapter_id, adapter_version))
        if adapter is None:
            raise BizoraError(
                ErrorCode.INVALID_REQUEST,
                f"Unknown adapter '{adapter_id}' version '{adapter_version}'.",
                details={
                    "adapter_id": adapter_id,
                    "adapter_version": adapter_version,
                    "available": [
                        {"adapter_id": key[0], "adapter_version": key[1]}
                        for key in sorted(self._adapters)
                    ],
                },
            )
        return adapter

    def available(self) -> tuple[tuple[str, str], ...]:
        """Return the registered (adapter_id, adapter_version) pairs."""
        return tuple(sorted(self._adapters))


def create_default_registry() -> AdapterRegistry:
    """Return a registry with the built-in execution adapters."""
    from bizora.adapters.deterministic_test import DeterministicTestAdapter
    from bizora.adapters.ngspice_adapter import NgspiceAdapter
    from bizora.adapters.torch_adapter import TorchTrainAdapter

    return AdapterRegistry(
        [DeterministicTestAdapter(), NgspiceAdapter(), TorchTrainAdapter()]
    )


def adapter_availability(adapter: ExecutionAdapter) -> tuple[bool, str | None]:
    """Report whether this host can execute an adapter right now.

    Local execution truth only: remote backends are selected per-run.
    """
    from bizora.adapters.ngspice_runner import resolve_ngspice
    from bizora.adapters.torch_adapter import torch_version

    if adapter.adapter_id == "bizora.torch-train":
        if torch_version() is None:
            return False, "torch is not installed in the execution environment."
        return True, None
    if adapter.adapter_id == "bizora.ngspice":
        if resolve_ngspice() is None:
            return False, "No ngspice binary found on PATH or at the known location."
        return True, None
    return True, None
