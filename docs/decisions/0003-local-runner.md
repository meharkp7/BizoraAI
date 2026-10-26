# ADR 0003: Local supervised execution boundary

- **Status:** Accepted
- **Decision:** Execute claimed runs out-of-process via a single trusted child
  entrypoint (`bizora.adapters.runner`) that resolves adapters through the
  default registry, runs them with a scrubbed environment in an ephemeral
  workspace, and returns a schema-validated result. The parent supervises with
  wall-clock timeouts, CPU/file limits, output caps, soft RSS polling,
  cancellation polling, and lease heartbeats, and finalizes through atomic
  compare-and-set so a concurrent cancel is never overwritten. Claim failures,
  timeouts, crashes, invalid results, and expired leases all become terminal
  `failed` runs with structured errors; a run is never automatically retried.
- **Context:** Phase A needs real execution before any remote provider. The
  local runner proves the claim/supervise/finalize protocol against the
  deterministic test adapter.
- **Consequences:** The local runner is a correctness and allowlist boundary,
  not a security sandbox. Verified on macOS: hard memory caps are
  unenforceable (`RLIMIT_AS`/`RLIMIT_RSS` have no effect), network isolation
  is unavailable (no working Seatbelt profile or container runtime), and CPU
  pinning does not exist. Safety here rests on executing only first-party
  allowlisted adapter code plus the enforceable limits above. Container or
  remote-provider isolation is required before running untrusted workloads.
- **Security defaults:** Child environment allowlist (`PATH`, `PYTHONPATH`,
  `PYTHONIOENCODING`); secrets never passed; stdin closed; stdout/stderr
  captured with byte caps; core dumps disabled; process-group kill on timeout,
  cancel, overflow, or lease loss.
