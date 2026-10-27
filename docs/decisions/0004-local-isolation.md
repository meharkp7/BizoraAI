# ADR 0004: Explicit isolation tiers with local fail-closed execution

- **Status:** Accepted
- **Decision:** Adapters declare an isolation tier (`local_trusted` or
  `isolated`, see `bizora.adapters.isolation`). The execution service and
  the local runner resolve the tier through a provider-neutral
  `IsolationProvider` interface and fail closed with a structured
  `isolation_unavailable` error when the active provider cannot satisfy
  it. The default `LocalIsolationProvider` satisfies only `local_trusted`
  first-party adapters. Any run with `network_access=True` requires the
  `isolated` tier, because local execution can neither provision nor gate
  network access.
- **Context:** Threat review of the local runner found it inherits the
  user's full filesystem and network access, runs as the same UID with no
  sandbox profile or container, and enforces only supervision limits
  (timeouts, output caps, FD limits, soft RSS polling). Those controls
  are a correctness and allowlist boundary, not a security sandbox (see
  ADR 0003). Genuine isolation is unavailable in the current environment,
  so local execution is explicitly restricted instead of implicitly
  trusted.
- **Consequences:** Only first-party local-trusted adapter code runs
  locally; undeclared tiers default to `isolated` (fail closed);
  network-capable and third-party workloads are rejected with an
  actionable error instead of running unsupervised. A container or
  remote backend can later implement `IsolationProvider` without
  rewriting the experiment lifecycle; its normative requirements
  checklist lives on that protocol's docstring.
- **Security defaults:** No arbitrary model-generated code or
  user-supplied executables are ever executed; exact adapter id/version
  allowlisting is unchanged; isolation rejections are terminal run
  failures, never silent downgrades.
