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

    return AdapterRegistry([DeterministicTestAdapter(), NgspiceAdapter()])
