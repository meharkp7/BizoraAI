"""Out-of-process entrypoint for allowlisted adapter execution.

Trusted parents spawn `python -m bizora.adapters.runner <request.json>
<result.json>`. The runner resolves the adapter through the default registry,
executes the request, and writes the validated result. Exit 0 means a result
was written, even for adapter-level failure; exit 2 means the runner itself
failed and no result can be trusted.
"""

import json
import sys

from pydantic import ValidationError

from bizora.adapters.isolation import (
    IsolationRequirement,
    LocalIsolationProvider,
    requirement_of,
)
from bizora.adapters.registry import AdapterRegistry, create_default_registry
from bizora.contracts.execution import AdapterExecutionRequest, ExecutionResult
from bizora.core.errors import BizoraError


def run_adapter(
    request_path: str,
    result_path: str,
    *,
    registry: AdapterRegistry | None = None,
) -> ExecutionResult:
    """Execute one request and write the validated result file."""
    with open(request_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    request = AdapterExecutionRequest.model_validate(payload)
    active = registry if registry is not None else create_default_registry()
    adapter = active.resolve(request.config.adapter_id, request.config.adapter_version)
    requirement = requirement_of(adapter)
    if request.config.network_access:
        requirement = IsolationRequirement.ISOLATED
    if not LocalIsolationProvider().supports(requirement):
        raise ValueError(
            f"Adapter '{request.config.adapter_id}' requires "
            f"'{requirement.value}' isolation; the local runner "
            "cannot satisfy it."
        )
    result = adapter.execute(request)
    if result.run_id != request.run_id:
        raise ValueError("Adapter returned a result for a different run.")
    validated = ExecutionResult.model_validate(result.model_dump(mode="json"))
    with open(result_path, "w", encoding="utf-8") as handle:
        handle.write(validated.model_dump_json())
    return validated


def main(argv: list[str]) -> int:
    """Run the adapter child process; return its exit code."""
    if len(argv) != 3:
        print(
            "usage: python -m bizora.adapters.runner <request.json> <result.json>",
            file=sys.stderr,
        )
        return 2
    try:
        run_adapter(argv[1], argv[2])
    except (OSError, ValueError, ValidationError, BizoraError) as exc:
        print(f"adapter runner failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
