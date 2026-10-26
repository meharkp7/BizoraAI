# ADR 0001: Contract-first modular monolith

- **Status:** Accepted for the hackathon foundation
- **Decision:** Begin as a modular Python domain/API codebase with explicit provider and worker boundaries. Keep shared contracts provider-neutral. Split deployables only when scale, security, or operational requirements justify it.
- **Context:** A short build window makes premature microservices and duplicated schemas expensive. At the same time, the product needs clean boundaries between untrusted documents, model-generated suggestions, graph edits, and compute execution.
- **Consequences:** One source of truth for schemas; easier contract testing; lower local setup burden. Deployable boundaries remain documented so workers can later be separated without rewriting domain types.
- **Guardrails:** No provider SDK types in public domain contracts; no unrestricted generated code execution; graph revisions are immutable; experiments are reproducibility records.
