# ADR 0002: Allowlisted experiment adapters

- **Status:** Accepted
- **Decision:** A model may propose a declarative graph patch or adapter configuration, but it may not submit arbitrary executable code to a worker. The compiler maps supported graph configurations to registered adapters. Unsupported changes are rejected with actionable validation errors.
- **Context:** Bizora needs real experiments without turning paper text, model output, or uploaded repositories into arbitrary code execution.
- **Consequences:** Initial architecture/model support is intentionally narrow. New adapter capabilities require explicit schemas, compatibility checks, tests, resource limits, and versioning.
- **Security defaults:** Network disabled unless an adapter explicitly needs an allowlisted endpoint; bounded CPU/GPU, memory, runtime and storage; ephemeral job workspace; secrets never mounted into untrusted workloads; dataset permissions checked before scheduling.
