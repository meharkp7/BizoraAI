# Bizora

**Turn any research paper, from any technical domain, into an explorable, evidence-grounded and experimentally testable methodology.**

Bizora is a research workspace that transforms scientific papers into interactive methodology models. Researchers can inspect components, trace claims to their sources, propose supported changes, execute real experiments on isolated compute, and compare measured results.

## Product in one paragraph

Bizora takes any research paper from any technical domain (ML/DL, electronics and PCB, IoT, robotics, mechanical, and more), auto-detects what kind of paper it is, regenerates its methodology as an evidence-linked, editable model, shows it as a realistic 3D build (a real-looking board with real components for electronics; layered blocks with real tensor shapes for ML), lets the researcher add, replace or modify components and techniques, runs the modified design for real on isolated compute, and shows measured results next to the baseline. An AI copilot answers questions grounded in the paper, the design and the runs.

## Rule zero: nothing is hard-coded

Bizora must work on papers nobody has seen yet. Test papers are inputs for measuring quality, never special cases in code.

- No domain list in core code. A domain is a label the model produces for each paper; packs declare which labels they handle.
- No paper-specific, part-specific or demo-specific branches. Part names, models and parameters live in data, never in logic.
- Every feature is accepted on held-out papers that were not used while building it.
- When extraction meets something unknown, it returns *assumed* or *unsupported* with a reason, never a guess presented as fact.

## Core workflow

1. **Ingest** a scientific paper: text, figures, equations, tables and metadata.
2. **Detect** the paper's domains as open-vocabulary, multi-label tags and select the matching domain pack automatically.
3. **Extract** methodology as a structured graph of components and relationships, grounded in paper evidence.
4. **Resolve** parts to real models through the pack's resolver ladder (exact part, family/package, category).
5. **Render** a realistic 3D build from the pack's render specs — no generic shapes.
6. **Modify** components or techniques through validated, versioned patches with pack preflight checks.
7. **Execute** real experiments through allowlisted adapters on isolated compute.
8. **Compare** measured results against the baseline and the paper's reported numbers.

## Core principles

- Evidence before explanation: claims must link to paper evidence, a measured run, or be labelled *assumed*/*illustrative*.
- No fabricated results: distinguish measured results, estimates and hypotheses.
- Immutable history: edits create new graph versions rather than silently overwriting prior work.
- Domain-agnostic core: graph, evidence, versions, patches, runs, comparison and copilot live in the core; every domain is a pack.
- Validated execution: proposed changes must pass schema, compatibility and resource checks before execution.
- Safe by design: never execute arbitrary model-generated code; heavy or untrusted compute runs isolated.
- Reproducibility: record dataset revisions, code revisions, seeds, configurations and execution metadata.
- Provider independence: model and compute providers must be replaceable behind stable internal interfaces.
- Testable contracts: changes to shared schemas require corresponding tests and documented migration decisions.

## Domain packs

The core knows nothing about any specific domain. Each domain pack provides: a component vocabulary, a part resolver, a 3D renderer, simulator adapters, compatibility rules, and copilot tools. Launch packs are ML/DL and Electronics. Adding a new pack requires zero changes to core code.

## Evaluation

Extraction quality is measured on a hand-checked gold set (see `tests/gold/README.md`), never on fixtures used while building. Run the harness with:

```sh
python -m bizora.eval_gold
```

## Provider responsibilities

- **Muse (Meta):** the coding agent that writes and tests the code, and the Model API (Muse Spark) for extraction, figure and PDF understanding, domain detection and the copilot.
- **Baseten:** optional second provider and fallback for hosted open models, behind the same provider interface.
- **Modal:** all heavy or untrusted compute: ML training, ngspice, firmware emulation, physics, KiCad 3D export, PDF parsing in a sandbox.

Provider integrations must remain optional where practical. Credentials, provider-specific settings and deployment assumptions must not be embedded in core domain logic.

## Engineering standards

- Define contracts before implementing dependent services.
- Keep domain logic independent of external AI and compute providers.
- Validate all external inputs and uploaded artifacts.
- Use pinned dependencies, automated tests, linting, formatting and type checking.
- Keep secrets out of source control. Never read or print `.env`.
- Record architectural decisions and breaking schema changes.
- Never claim an experiment is reproducible unless the available evidence and execution artifacts justify that claim.
- Done means the acceptance test passes, not that the code exists.

## Development status

Bizora is under active development. Features must be described as implemented only after their code and acceptance tests have been verified. The authoritative build plan is `docs/BUILD_BRIEF.md`.

## License

To be decided before public release.
