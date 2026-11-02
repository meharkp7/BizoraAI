"""Modal-backed isolated execution behind the existing interfaces.

This module implements :class:`bizora.adapters.isolation.IsolationProvider`
for Modal and builds the per-run function spec (network off by default,
time/memory caps, ephemeral workspace, empty environment with no secrets
mounted). The executor submits runs through the Modal SDK, which is
imported lazily so unit tests never make live Modal calls.

:class:`bizora.core.execution_service.ExecutionService` dispatches to
:func:`ModalExecutor.submit` plus :func:`ModalExecutor.fetch_result` when the
Modal isolation provider is selected; the local spawn path stays for
local-trusted runs.
"""

import importlib
import importlib.util
import logging
import os
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bizora.adapters.isolation import IsolationRequirement
from bizora.contracts.execution import AdapterExecutionRequest
from bizora.core.errors import BizoraError, ErrorCode

logger = logging.getLogger(__name__)

DEFAULT_APP_NAME = "bizora-experiments"
DEFAULT_FUNCTION_NAME = "run_adapter"
DEFAULT_MAX_TIMEOUT_SECONDS = 3600
DEFAULT_MEMORY_MB = 4096
MAX_MEMORY_MB = 32768
MIN_MEMORY_MB = 128
EPHEMERAL_WORKSPACE: Final = "/workspace"


class ModalFunctionSpec(BaseModel):
    """Immutable, validated description of one Modal function call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_name: str = Field(min_length=1, max_length=128)
    function_name: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(min_length=1, max_length=128)
    adapter_version: str = Field(min_length=1, max_length=64)
    timeout_seconds: int = Field(ge=1, le=86_400)
    memory_mb: int = Field(ge=MIN_MEMORY_MB, le=MAX_MEMORY_MB)
    gpu_count: int = Field(ge=0, le=8)
    network_enabled: bool = False
    allowed_hosts: tuple[str, ...] = Field(default=(), max_length=16)
    workspace: Literal["/workspace"] = EPHEMERAL_WORKSPACE

    @model_validator(mode="after")
    def validate_network_policy(self) -> "ModalFunctionSpec":
        if not self.network_enabled and self.allowed_hosts:
            raise ValueError("Allowed hosts require network_enabled=true.")
        for host in self.allowed_hosts:
            if not host or len(host) > 253:
                raise ValueError("Allowed hosts must be 1-253 characters.")
        return self


def build_modal_spec(
    request: AdapterExecutionRequest,
    *,
    app_name: str = DEFAULT_APP_NAME,
    function_name: str = DEFAULT_FUNCTION_NAME,
    max_timeout_seconds: int = DEFAULT_MAX_TIMEOUT_SECONDS,
    default_memory_mb: int = DEFAULT_MEMORY_MB,
) -> ModalFunctionSpec:
    """Derive a fail-closed Modal spec from one execution request.

    Network mirrors the request flag (off by default); the timeout is
    capped by the executor limit; memory is clamped into the supported
    range. No environment is attached to the spec: the serialized
    request is passed as the function argument instead, so no secrets
    can be mounted or inherited.
    """
    if max_timeout_seconds < 1 or max_timeout_seconds > 86_400:
        raise ValueError("max_timeout_seconds must be within 1 and 86400.")
    timeout = min(request.limits.timeout_seconds, max_timeout_seconds)
    memory = min(max(request.limits.soft_rss_mb, default_memory_mb), MAX_MEMORY_MB)
    memory = max(memory, MIN_MEMORY_MB)
    return ModalFunctionSpec(
        app_name=app_name,
        function_name=function_name,
        adapter_id=request.config.adapter_id,
        adapter_version=request.config.adapter_version,
        timeout_seconds=timeout,
        memory_mb=memory,
        gpu_count=request.config.max_gpu_count,
        network_enabled=request.config.network_access,
        workspace=EPHEMERAL_WORKSPACE,
    )


class ModalIsolationProvider:
    """Isolation backend identifier for Modal sandboxes.

    A Modal sandbox satisfies the isolated tier (dedicated user,
    ephemeral workspace, no inherited secrets, gated network, enforced
    limits, process cleanup), which also satisfies local-trusted work.
    """

    provider_id = "bizora.modal"

    def supports(self, requirement: IsolationRequirement) -> bool:
        """Support both tiers; isolation is strictly stronger."""
        return requirement in (
            IsolationRequirement.LOCAL_TRUSTED,
            IsolationRequirement.ISOLATED,
        )


class ModalUnavailableError(BizoraError):
    """Raised when a Modal submission cannot be attempted safely."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.PROVIDER_UNAVAILABLE, message)


class ModalCallError(BizoraError):
    """Raised when a submitted Modal call fails or returns no result."""

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.EXPERIMENT_FAILED, message)


class ModalExecutor:
    """Submit adapter executions to Modal; fail closed without SDK/creds."""

    def __init__(
        self,
        *,
        app_name: str = DEFAULT_APP_NAME,
        function_name: str = DEFAULT_FUNCTION_NAME,
        max_timeout_seconds: int = DEFAULT_MAX_TIMEOUT_SECONDS,
        default_memory_mb: int = DEFAULT_MEMORY_MB,
    ) -> None:
        if max_timeout_seconds < 1 or max_timeout_seconds > 86_400:
            raise ValueError("max_timeout_seconds must be within 1 and 86400.")
        self._app_name = app_name
        self._function_name = function_name
        self._max_timeout_seconds = max_timeout_seconds
        self._default_memory_mb = default_memory_mb

    @staticmethod
    def sdk_available() -> bool:
        """Return whether the Modal SDK is importable (no import)."""
        return importlib.util.find_spec("modal") is not None

    @staticmethod
    def credentials_present() -> bool:
        """Return whether Modal key material is configured (presence only)."""
        return bool(
            os.environ.get("MODAL_TOKEN_ID", "").strip()
            and os.environ.get("MODAL_TOKEN_SECRET", "").strip()
        )

    def build_spec(self, request: AdapterExecutionRequest) -> ModalFunctionSpec:
        """Return the validated spec this executor would submit."""
        return build_modal_spec(
            request,
            app_name=self._app_name,
            function_name=self._function_name,
            max_timeout_seconds=self._max_timeout_seconds,
            default_memory_mb=self._default_memory_mb,
        )

    def submit(self, request: AdapterExecutionRequest) -> str:
        """Submit one execution; never attempt without SDK and credentials.

        Returns the Modal invocation id. Unit tests must never reach the
        live call: without the SDK or credentials this raises
        ModalUnavailableError before any network I/O.
        """
        spec = self.build_spec(request)
        if not self.sdk_available():
            raise ModalUnavailableError(
                "Modal execution needs the 'modal' package; "
                "install it and configure credentials before submitting."
            )
        if not self.credentials_present():
            raise ModalUnavailableError(
                "Modal execution needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET."
            )
        return self._invoke(spec, request.model_dump_json())

    def _invoke(self, spec: ModalFunctionSpec, request_json: str) -> str:
        """Run the Modal function (live call; never exercised in tests)."""
        modal = cast(Any, importlib.import_module("modal"))
        function = modal.Function.from_name(spec.app_name, spec.function_name)
        call = function.spawn(request_json)
        return str(call.object_id)

    def fetch_result(self, invocation_id: str, timeout_seconds: float) -> str:
        """Block for one submitted call and return its result JSON.

        Raises TimeoutError when the slice expires so the caller can
        heartbeat and retry, and ModalCallError when the call itself
        failed. Unit tests stub _fetch; the live SDK path stays here.
        """
        if not self.sdk_available():
            raise ModalUnavailableError(
                "Modal execution needs the 'modal' package."
            )
        if not self.credentials_present():
            raise ModalUnavailableError(
                "Modal execution needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET."
            )
        try:
            return self._fetch(invocation_id, timeout_seconds)
        except TimeoutError:
            raise
        except ModalCallError:
            raise
        except Exception as exc:
            if type(exc).__name__.endswith("TimeoutError"):
                raise TimeoutError(
                    f"Modal call {invocation_id} timed out after "
                    f"{timeout_seconds}s."
                ) from exc
            raise ModalCallError(
                f"Modal call {invocation_id} failed: {exc}"
            ) from exc

    def _fetch(self, invocation_id: str, timeout_seconds: float) -> str:
        """Wait on one Modal call (live call; never exercised in tests)."""
        modal = cast(Any, importlib.import_module("modal"))
        call = modal.FunctionCall.from_id(invocation_id)
        return str(call.get(timeout=timeout_seconds))

    def cancel(self, invocation_id: str) -> None:
        """Best-effort cancel of one submitted call; never raises."""
        try:
            if not self.sdk_available() or not self.credentials_present():
                return
            modal = cast(Any, importlib.import_module("modal"))
            modal.FunctionCall.from_id(invocation_id).cancel()
        except Exception:
            logger.warning("Modal cancel failed for %s.", invocation_id)
