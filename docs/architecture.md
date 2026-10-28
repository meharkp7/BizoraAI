# Architecture and service boundaries

Scope follows `docs/BUILD_BRIEF.md`: multi-domain, pack-based, realistic 3D, real execution.

## Product loop

1. **Upload** a paper, then **Ingest** (parse text, figures, equations, tables).
2. **Extract** with a vision-language model: domain tags, components, connections, parameters, evidence locators with confidence, and **assumed** flags for anything the paper does not state.
3. **Graph**: validate and version the methodology graph. A graph revision is immutable; changes are declarative patches against a known base revision.
4. **Pack**: select the domain pack automatically from the paper's domain tags; papers with no matching pack open in explore-only mode with a clear message.
5. **Resolve** parts to real models through the pack's resolver ladder (exact part, family/package, category), each labelled *from paper*, *matched* or *assumed*.
6. **Render** realistic 3D from pack render specs (physical board and real component models for electronics; layers with real tensor shapes for ML). Nothing renders as a generic shape.
7. **Edit** with pack preflight (tensor-shape rules for ML; voltage/pin/electrical rules for circuits); every edit is a versioned patch.
8. **Run** on isolated compute through allowlisted adapters only; stream telemetry back and tag every animation **measured** or **illustrative**.
9. **Compare** measured baseline-vs-variant results with the paper's reported numbers shown separately.
10. **Copilot**: an LLM with tools over paper evidence, graph, diffs, runs and parts proposes patches; it never writes without user approval and cites its sources.

## Logical components

- Web client: project workspace, source viewer, pack-driven 2D/3D explorer, evidence panel, experiment comparison, copilot with approval gate.
- API: authentication/authorization, project lifecycle, upload metadata, graph versions, patch validation, experiment submission and status.
- Domain-agnostic core: provider-neutral Pydantic contracts, graph engine (invariants, patch application, version lineage, compatibility checks), run lifecycle with leases and recovery, baseline comparison. The core names no domain, part, or paper.
- Domain packs: per-domain modules behind the Pack interface (`detect`, `vocabulary`, `resolve_part`, `render_spec`, `simulators`, `preflight_rules`, `copilot_tools`). Launch packs: ML/DL and Electronics.
- Ingestion workers: PDF parsing and figure/equation/table extraction; isolated from experiment workers.
- Intelligence adapters: model-provider clients, structured extraction, segmentation, evidence alignment. Providers are replaceable behind interfaces.
- Asset registry: per-part 3D model (GLB), footprint, pin map, license and source, with procedural fallbacks for common packages.
- Compiler/adapter registry: allowlisted architectures and operations only; first-party templates, never model-written code.
- Experiment workers: ephemeral, quota-limited, isolated jobs (Modal); network disabled by default; no arbitrary generated code execution.
- Persistence: relational metadata store for projects/versions/runs; object storage for PDFs, datasets, checkpoints, logs, and result artifacts. Do not put large binaries in relational rows.
- Queue and observability: idempotent job dispatch, retry policy, structured logs, metrics, trace/run IDs, timeout and cancellation.

## State and data ownership

- Graph versions are append-only. `parent_version` points to the prior revision.
- Every patch names `base_graph_id` and `base_version`; stale patches must fail with a conflict rather than silently overwrite a newer graph.
- Experiment configuration snapshots a graph version and dataset revision at submission time.
- Result records are immutable once finalized; corrections create a new result revision with an audit trail.
- The paper is evidence, not executable authority. A paper's code snippets or uploaded files must never be executed directly.

## Evaluation

Extraction quality is measured on a hand-checked gold set (`tests/gold/`): at least 15 papers across at least 5 domains, with at least 5 held-out papers used only for testing. The harness (`python -m bizora.eval_gold`) prints domain accuracy and component precision/recall. Features pass only on held-out papers.

## Scope boundaries

**In scope:** any research paper from any technical domain via domain packs; open-vocabulary multi-label domain detection; evidence-linked methodology graphs; realistic pack-driven 3D; real experiments on isolated compute; versioned editing with preflight; live telemetry; grounded copilot.

**Not promised:** reproduction of every paper (the tool must say when it cannot); exact copper routing from a figure (imported board files give the real layout, otherwise layout is illustrative); mechanical FEA, hardware-in-the-loop IoT and large-scale training before the launch packs.
