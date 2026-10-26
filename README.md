
# Bizora

**Turn scientific research into explorable, evidence-grounded and experimentally testable methodology.**

Bizora is a research workspace that transforms scientific papers into interactive methodology graphs. Researchers can inspect model components, trace architectural claims to their sources, propose supported changes, execute controlled experiments and compare measured results.

## Core workflow

1. **Ingest** a scientific paper and extract its text, figures, equations and relevant metadata.
2. **Reconstruct** its methodology as a structured graph of components and relationships.
3. **Ground** graph elements in evidence from the original paper, recording uncertainty where interpretation is ambiguous.
4. **Explore** the methodology through an interactive 2D graph, with 3D exploration as a later extension.
5. **Modify** supported components or parameters through validated, versioned changes.
6. **Execute** compatible experiments using approved implementations and controlled compute jobs.
7. **Compare** measured results against a baseline, preserving configurations, logs, artifacts and reproducibility information.

## Core principles

- Evidence before explanation: scientific claims must link to supporting sources.
- No fabricated results: distinguish measured results, estimates and hypotheses.
- Immutable history: edits create new graph versions rather than silently overwriting prior work.
- Validated execution: proposed changes must pass schema, compatibility and resource checks before execution.
- Safe by design: never execute arbitrary model-generated code directly on the host.
- Reproducibility: record dataset revisions, code revisions, seeds, configurations and execution metadata.
- Provider independence: model and compute providers must be replaceable behind stable internal interfaces.
- Testable contracts: changes to shared schemas require corresponding tests and documented migration decisions.

## Initial scope

The first executable workflow will focus on a supported vision-transformer architecture using an existing open-source implementation.

The first release prioritizes:
- Structured methodology graph contracts
- Source evidence and provenance
- Graph validation and immutable versioning
- A supported architecture modification path
- Controlled experiment execution
- Baseline-versus-variant evaluation

Additional model families, advanced 3D visualization and broader automation will follow only after the core workflow is validated.

## Provider responsibilities

- **Muse Code:** coding assistance for implementation, testing, refactoring and debugging.
- **Fireworks AI:** evaluate suitable models and retrieval components for research extraction and evidence discovery.
- **Baseten:** optional persistent inference serving for selected models.
- **Modal:** isolated compute jobs for training, evaluation and experiment execution.

Provider integrations must remain optional where practical. Credentials, provider-specific settings and deployment assumptions must not be embedded in core domain logic.

## Engineering standards

- Define contracts before implementing dependent services.
- Keep domain logic independent of external AI and compute providers.
- Validate all external inputs and uploaded artifacts.
- Use pinned dependencies, automated tests, linting, formatting and type checking.
- Keep secrets out of source control.
- Record architectural decisions and breaking schema changes.
- Never claim an experiment is reproducible unless the available evidence and execution artifacts justify that claim.

## Development status

Bizora is under active development. Features must be described as implemented only after their code and acceptance tests have been verified.

## License

To be decided before public release.
