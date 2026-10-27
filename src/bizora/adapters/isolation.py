"""Provider-neutral execution isolation tiers.

Local subprocess supervision (timeouts, output caps, allowlisted
adapters) is a correctness boundary, not a security sandbox: the child
runs as the same user with the same filesystem and network access.
Adapters therefore declare the isolation tier they require, and local
execution fails closed for anything it cannot satisfy.
"""

from enum import StrEnum
from typing import Protocol, runtime_checkable


class IsolationRequirement(StrEnum):
    """Isolation tier an adapter requires for safe execution."""

    LOCAL_TRUSTED = "local_trusted"
    ISOLATED = "isolated"


@runtime_checkable
class IsolationProvider(Protocol):
    """Interface implemented by execution isolation backends.

    A production isolated backend MUST enforce, at minimum:
    - non-root, dedicated execution user;
    - read-only base filesystem with a per-run writable workspace;
    - no inherited secrets or credentials in the environment;
    - network denied by default, with allowlisted endpoints only;
    - wall-clock, CPU, memory, and disk limits with cleanup;
    - guaranteed process-tree cleanup on timeout, cancel, or failure;
    - bounded captured output and artifact handling;
    - execution limited to explicitly registered adapters with
      schema-validated requests and results.
    """

    @property
    def provider_id(self) -> str:
        """Return the stable provider identifier."""
        ...

    def supports(self, requirement: IsolationRequirement) -> bool:
        """Return whether this backend can satisfy a requirement."""
        ...


class LocalIsolationProvider:
    """Local subprocess supervision: trusted first-party code only.

    This provider satisfies LOCAL_TRUSTED adapters and rejects
    everything else. It is NOT a security sandbox and must never be
    claimed as one.
    """

    provider_id = "bizora.local"

    def supports(self, requirement: IsolationRequirement) -> bool:
        """Support only explicitly local-trusted adapters."""
        return requirement == IsolationRequirement.LOCAL_TRUSTED


def requirement_of(adapter: object) -> IsolationRequirement:
    """Return an adapter's declared tier, failing closed when undeclared."""
    requirement = getattr(adapter, "isolation_requirement", None)
    if isinstance(requirement, IsolationRequirement):
        return requirement
    return IsolationRequirement.ISOLATED
