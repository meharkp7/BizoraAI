# BizoraAI: Production Build Brief

*Target results first, then the steps to reach them, then ready-to-paste instructions for Muse Code. Written 28 Oct 2026, based on the repository review in the companion doc "BizoraAI: State Evaluation and Path to the Vision".*

**How to use this doc:** save it in the repo as `docs/BUILD_BRIEF.md`. At the start of every Muse session, tell Muse: *"Read docs/BUILD\_BRIEF.md first. Work only on the phase I name."* Part C has the exact prompts.

## Rule zero: nothing is hard-coded

Bizora must work on papers nobody has seen yet. Test papers are inputs for measuring quality, never special cases in code.

- No domain list in core code. A domain is a label the model produces for each paper; packs declare which labels they handle.
- No paper-specific, part-specific or demo-specific branches (nothing like `if "ESP32" in text`). Part names, models and parameters live in data (asset registry, pack vocabulary), never in logic.
- Every feature is accepted on **held-out papers** that were not used while building it. A feature that passes only on its own examples counts as failed.
- When extraction meets something unknown, it returns *assumed* or *unsupported* with a reason, never a guess presented as fact.
- Test fixtures may name real parts and papers; production code may not.

## 1. Product in one paragraph

Bizora takes **any research paper from any technical domain** (ML/DL, electronics and PCB, IoT, robotics, mechanical, and more), **auto-detects what kind of paper it is**, regenerates its methodology and architecture as an **evidence-linked, editable model**, shows it as a **realistic 3D build** (a real-looking board with real components for electronics; a layered machine with real tensor shapes for ML), lets the researcher **add, replace or modify components and techniques**, **runs the modified design for real** on isolated compute, and shows **measured results** next to the baseline. An **AI copilot** answers questions grounded in the paper, the design and the runs.

This is a production-grade build, not a prototype. Every claim in the UI must be traceable to the paper (evidence) or to a real run (measured). Anything else is labelled *assumed* or *illustrative*.

---

# PART A: Results we must obtain

Each result has a measurable acceptance test. "Done" means the test passes, not that the code exists.

## R1. Any paper in, domain detected automatically

- Domain is **open-ended and multi-label**, produced by the model at extraction time (for example: "embedded IoT", "analog circuit", "vision transformer"). There is **no hard-coded domain list** in the core.
- If a matching domain pack exists, it is selected automatically. If none exists, the paper still opens in explore-only mode with a clear message.
- **Acceptance:** on a gold set of at least 15 papers covering at least 5 domains, the correct primary domain is detected for at least 90%, and no paper crashes the pipeline.

## R2. Evidence-linked methodology graph

- Every node and edge links to a page, quote, figure label or URL in the paper. Anything the paper does not state is flagged **assumed** with a confidence value, and the researcher can correct it.
- **Acceptance (targets, tune after the first measurement):** against hand-checked gold graphs, component recall at least 80% and precision at least 85%; 100% of nodes have evidence or an explicit *assumed* flag.

## R3. Figures, diagrams, equations and tables understood

- Architecture figures, circuit diagrams, block diagrams, equations and tables are parsed with a vision model, not just plain text.
- **Acceptance:** on the gold set, the share of components that appear only in figures and are still recovered is measured and reported; target at least 60% at first release.

## R4. Domain packs (the generality mechanism)

- The core is domain-agnostic: graph, evidence, versions, patches, runs, comparison, copilot. Each domain is a **pack** with: a component vocabulary, a part resolver, a 3D renderer, simulator adapters, compatibility rules, and copilot tools.
- **Launch packs:** ML/DL and Electronics (chosen because they are the most different from each other; if one core serves both, robotics, mechanical and IoT are additional packs rather than rewrites).
- **Acceptance:** adding a new minimal pack requires zero changes to core code, proven by a test that registers a toy pack.

## R5. Realistic 3D

- **Electronics:** a physical-looking PCB with real component models (an ESP32 DevKit looks like an ESP32 DevKit, a motion sensor like the actual sensor module, resistors and transistors in their real packages). Real board files (KiCad/Gerber) are imported when the paper provides them; otherwise the board is **generated** from the BOM and connectivity and labelled *illustrative layout*.
- **ML/DL:** layers drawn as physical blocks with real tensor dimensions; data visibly flows through during a run.
- **Part resolver ladder:** exact part number, then family/package, then category representative. Each resolved part shows its confidence (*from paper*, *matched*, *assumed*).
- **Acceptance:** for any held-out electronics paper that lists its parts, at least 90% of the components in the BOM render as their real model or package, and none render as generic shapes.

## R6. Real experiments on real compute

- Runs execute on isolated compute (Modal), never on the API host, and never run model-generated code. Each run stores seed, environment, code revision, dataset revision, logs, metrics and artifacts.
- **Acceptance:** an edited ML graph trains and returns a metric curve that **changes** when a component is changed; an edited circuit returns SPICE waveforms that change when a resistor value changes.

## R7. Experiment workspace

- Add, remove or replace components and techniques, not just tune parameters. Every edit is a versioned patch. A **preflight** check blocks incompatible edits before running (tensor-shape mismatch for ML, voltage/pin/electrical rules for circuits). Baseline vs variant comparison with the original paper's reported numbers shown separately from measured numbers.
- **Acceptance:** 10 scripted edits per launch pack, each either runs successfully or is rejected by preflight with a clear reason.

## R8. Live simulation view

- Run telemetry streams to the browser in real time and drives the 3D view (signal pulses on traces, voltages, gradient or activation statistics, loss curve). Every animation is tagged **measured** (from a real run) or **illustrative**.
- **Acceptance:** telemetry appears in the UI within 2 seconds of being produced; stopping a run stops the stream.

## R9. Grounded AI copilot

- An LLM copilot with tools: read paper evidence, inspect the graph and diffs, query runs and metrics, search the part library, run preflight, and **propose** patches. It never applies changes without user approval and cites the evidence or run it used.
- **Acceptance:** a set of at least 30 test questions ("why did this run diverge?", "what did the paper say about this resistor value?") answered with correct citations at least 85% of the time, and zero unapproved writes.

## R10. Production readiness

Postgres, object storage for PDFs and artifacts, a job queue, authentication and project ownership, secrets management, rate limits and cost caps, structured logging and tracing, CI that blocks merges on test/lint/type failures, a security review (untrusted PDFs are parsed in isolation), and a runbook.

## Non-goals and honest limits

- We do **not** promise that every paper can be reproduced; the tool must say when it cannot.
- Exact copper routing is not recoverable from a figure; imported board files give the real layout, otherwise layout is illustrative.
- Mechanical FEA, hardware-in-the-loop IoT and large-scale training come after the launch packs.

---

# PART B: Steps to obtain the results

## Architecture at a glance

**Upload** a paper, then **Ingest** (parse text, figures, equations, tables), then **Extract** with a vision-language model (domain, components, connections, evidence), then **Graph** (versioned, validated), then **Pack** (selected automatically by domain), then **Resolve** parts to real models, **Render** 3D, **Edit** with preflight, **Run** on isolated compute, **Telemetry** streamed back, **Compare** against baseline, with the **Copilot** reading all of it.

## How your three credits are used

| Provider | Used for | Notes |
| --- | --- | --- |
| **Muse (Meta)** | The coding agent (Muse Code) that writes and tests the code, and the Model API (Muse Spark) for extraction, figure and PDF understanding, domain detection and the copilot | Spend on well-specified tasks, not exploration |
| **Baseten** | Optional second provider and fallback for hosted open models; its usage is not visible in your dashboard yet, so plan without it until confirmed | Keep it behind the same provider interface; not on the critical path |
| **Modal** | All heavy or untrusted compute: ML training, ngspice, firmware emulation, physics, KiCad 3D export, PDF parsing in a sandbox | Scale to zero; set per-run time and cost caps |

The existing code already has provider interfaces for extraction (Fireworks/Baseten) and configuration fields for Modal, but **no Modal client exists yet** and Muse's API is not wired as a provider. Those are build tasks below.

## Muse API: confirmed capabilities and credit plan

Meta's [Models page](https://dev.meta.ai/docs/models) confirms that Muse Spark (version 1.3 is the recommended one for new work) accepts text, image, video and PDF input, returns text, and supports tool calling and structured output through the Responses, Chat Completions and Messages APIs. So **figure, diagram and PDF understanding can run on Muse directly, with no separate vision model.** Meta also hosts SAM 3.1 for segmentation, which may help locate components in diagrams; evaluate it in Phase 3.

- Use **Muse Spark** for high-volume extraction, domain detection and the copilot. Use **Muse Wonder** (stronger and costlier) only for hard reasoning steps; switching is a model ID change.
- Use the **Responses API** for PDF and image input, with structured output (JSON schema) so results are validated by the existing Pydantic contracts.
- Stated balances: about 140 Muse credits (unit not yet confirmed) and $100 of Modal credits.
- **Check before building:** "Muse credits" may mean Muse Code plan usage or a Model API pay-as-you-go balance; Meta bills them separately. Your earlier dashboard also showed a billing restriction. Run `muse usage` and open the Billing page to confirm which balance the API key draws from.
- Model availability varies by country; if API calls start failing with access errors, check Meta's Geographic Use Policy.
- **Budget guard:** on Modal, set per-run time and GPU caps and a spend alert well below $100. On Muse, cache extraction by paper hash, log tokens per call, and report spend at every phase gate.

## What to keep, change and remove from the current repo

- **Keep:** immutable graph versions and patch/conflict logic, run lifecycle with leases and recovery, baseline comparison, adapter registry and isolation tiers, contract-first schemas and ADRs, test and lint setup.
- **Change:** the hard-coded domain table and component catalog (becomes the Electronics pack data), the 2D/3D views (become pack-driven), the run panel (real adapters), the extraction pipeline (text-only becomes text plus vision).
- **Remove or replace:** the regex copilot (replaced by the LLM copilot, regex kept only as a fast path), box/cylinder/sphere node shapes in 3D (replaced by real models).

## Phase 0: Reset and baseline (1 to 2 days)

**Steps**

1. Commit or stash all uncommitted work. Rotate the Baseten key if the zip was shared; confirm with `git log --all -- .env` that the key was never committed.
2. Rewrite `README.md` and `docs/architecture.md` to this brief's scope. Add ADR 0005: "Domain-agnostic core with domain packs".
3. Build the **gold set**: at least 15 papers across at least 5 domains (for example an ESP32/IoT sensor system, an analog or power circuit with a PCB design, a vision transformer, a CNN, a robot arm controller, a quantization paper). For each, hand-write the expected domain, component list and a few evidence pointers. You supply the papers. Respect paper licenses and keep PDFs out of git. Keep at least 5 papers aside as held-out: they are never used while building, only to test.
4. Add an **evaluation harness**: a command that runs extraction on the gold set and prints domain accuracy and component precision/recall.

**Done when:** repo clean and committed, docs match scope, `make eval` (or equivalent) prints baseline numbers.

## Phase 1: Platform hardening (about 1 week)

**Steps**

1. Move from SQLite to Postgres for all environments; keep Alembic migrations.
2. Add S3-compatible object storage for PDFs, figures, artifacts and 3D assets (no large binaries in database rows).
3. Implement a **Modal executor** behind the existing `IsolationProvider` interface (network off by default, time/memory limits, ephemeral workspace, no secrets mounted).
4. Add a durable job queue and worker for ingestion and runs; idempotent dispatch, retries for ingestion (not for experiment runs, per ADR 0003).
5. Add authentication and project ownership checks on every endpoint.
6. CI pipeline: pytest, ruff, mypy, vitest, tsc, oxlint, Playwright; merges blocked on failure.

**Done when:** a run executes on Modal and its logs and artifacts appear in the UI; unauthenticated requests are rejected; CI is green.

## Phase 2: Domain-agnostic core (about 1 week)

**Steps**

1. Define the **Pack interface** (contract tests first): `detect`, `vocabulary`, `resolve_part`, `render_spec`, `simulators`, `preflight_rules`, `copilot_tools`.
2. Replace the hard-coded domain table with open-vocabulary domain tags stored on the graph; routing picks the best pack or falls back to explore-only mode.
3. Move the existing electronics catalog and fixtures into an **Electronics pack** module; delete any core code that names a specific domain.
4. Add the toy-pack test (R4 acceptance).

**Done when:** no domain names appear in core code; toy pack registers without core changes.

## Phase 3: Extraction v2 (about 1 to 2 weeks)

**Steps**

1. Ingestion: text with layout, figure and diagram extraction, equation extraction, table extraction, run in an isolated worker.
2. Call **Muse Spark 1.3 through the Responses API (image and PDF input), with Baseten kept as an optional fallback**; send figures and diagram crops with surrounding text.
3. Extraction output: domain tags, components, connections, parameters, evidence locators with confidence, **assumed** flags.
4. Add a human correction loop in the UI (accept, edit, reject each claim).
5. Cache extraction results by paper hash to save credits.
6. Iterate until the R1 to R3 acceptance numbers pass on the gold set.

**Done when:** `make eval` meets R1 to R3 targets.

## Phase 4: Part resolver and 3D asset library (about 1 week, runs in parallel with Phase 5 design)

**Steps**

1. Build the **asset registry**: for each part, a 3D model (GLB), a footprint, pin map, license and source. Seed from KiCad's official 3D library and open part libraries (check each license, some are CC-BY-SA and need attribution), plus modules such as ESP32 DevKit boards and common sensor breakouts.
2. Implement the resolver ladder (exact part, then family/package, then category) with confidence labels.
3. Procedural fallbacks for common packages (SOT-23, TO-92, SOIC, QFN, 0603 and 0805 passives) so that nothing renders as a generic shape.
4. Replace the box/cylinder/sphere rendering with a GLB loader.

**Done when:** R5 acceptance for components passes on the ESP32 demo paper.

## Phase 5: Electronics pack (about 2 to 3 weeks)

**Steps**

1. Netlist and BOM extraction from the graph; import KiCad/Gerber if the paper supplies them.
2. Board generation: outline, placement and simple traces from connectivity, labelled *illustrative layout*; optional export through KiCad's CLI on Modal for realistic 3D output.
3. Simulation: **ngspice** on Modal for analog; behavioral models for common sensors; for ESP32 firmware, evaluate Renode or QEMU emulation on Modal.
4. Electrical preflight: pin compatibility, voltage levels, missing pull-ups, power budget.
5. 3D view: board, components, traces; waveforms and voltages overlaid on the board from real runs.

**Done when:** a held-out electronics paper shows a physical board, runs a simulation, and changing a component changes the measured output.

## Phase 6: ML/DL pack (about 2 weeks, can run in parallel with Phase 5)

**Steps**

1. Allowlisted layer vocabulary: linear, convolution, normalization, activation, dropout, attention, MLP block, residual, embedding, pooling, positional encoding.
2. **Graph-to-PyTorch compiler** from first-party templates only; never model-written code.
3. Training and evaluation on Modal with small public datasets, fixed seeds and recorded environment.
4. Tensor-shape preflight for every edit.
5. 3D view: layers as physical blocks with real shapes; activation and gradient statistics animate during runs.

**Done when:** R6 and R7 pass for ML (an edit changes the metric curve; incompatible edits are rejected).

## Phase 7: Experiment workspace and live telemetry (about 1 to 2 weeks)

**Steps**

1. Stream run events over SSE or WebSocket (step, metrics, logs, pack-specific signals).
2. Add, replace and remove components from the pack vocabulary; versioned patches; baseline-vs-variant comparison with measured and paper-reported numbers shown separately.
3. Label every visual element *measured*, *assumed* or *illustrative*.

**Done when:** R7 and R8 pass.

## Phase 8: LLM copilot (about 1 week)

**Steps**

1. Implement the copilot behind the provider interface with the tool set from R9; cite evidence and runs in every answer.
2. Keep the human-approval gate for all changes.
3. Build the 30-question evaluation set and track citation accuracy.

**Done when:** R9 passes.

## Phase 9: More packs (each about 2 to 3 weeks, in priority order)

IoT systems (firmware and protocol emulation), robotics (PyBullet or MuJoCo), mechanical (start with simple dynamics before FEA). Each pack must follow the pack interface and ship with its own gold papers and acceptance tests.

## Phase 10: Production release

Observability (logs, traces, metrics, alerts), load and abuse testing of uploads, security review, cost dashboards and hard spending caps per user and per run, backup and restore, runbook, license review of all assets and libraries.

## Suggested order

Phase 0, then 1 and 2 together, then 3, then 4, then 5 and 6 in parallel, then 7, 8, 9, 10. If credits run short, protect this chain: **0, 2, 3, 4, 5 (first electronics papers), 6 (first ML papers), 7, 8**. That already delivers the full vision for two domains.

---

# PART C: Instructions to give Muse Code

## C0. One paste, all phases, with checkpoints

Give Muse this once. It works through the phases in order and **stops at the end of each phase**, so you can check the result and the spend before it continues. Reply "continue" to move on. The detailed task for each phase is in C2, and the rules are in C1.

```
Read docs/BUILD_BRIEF.md fully before doing anything. Then follow its "Suggested order" and the master rules in C1.
Work on exactly one phase at a time. For each phase:
1. Give a plan of at most 10 lines.
2. Implement it contract-first, with tests, in small commits.
3. Run pytest, ruff, mypy, vitest, tsc and oxlint, plus the phase's acceptance tests on held-out papers.
4. STOP and report in at most 15 lines: what changed, acceptance results (numbers), what is unverified, tokens or Modal spend used, and the next phase.
Do not start the next phase until I reply "continue".
Never hard-code domains, papers, parts or demos. If you are blocked by a missing paper, key, asset or decision, stop and ask once instead of inventing data.
Start with Phase 0.
```

## C1. Master brief (paste at the start of every session)

```
You are building BizoraAI as a production-grade system, not a prototype.
Read docs/BUILD_BRIEF.md first. Work ONLY on the phase or task I name.

Rules:
1. Contract-first: write or update Pydantic contracts and tests before implementation.
2. Never execute model-generated or paper-supplied code. Execution goes only through allowlisted first-party adapters, on isolated compute for anything beyond trusted code.
3. No hard-coding: no domain list, and no paper-specific, part-specific or demo-specific logic, in core or pack code. Domains are labels the model produces; part names and parameters live in data files, not in if-statements. Every feature must pass on held-out papers I supply, not only on its own fixtures.
4. Evidence before explanation: every claim links to paper evidence, a measured run, or is labelled assumed/illustrative. Never fabricate results.
5. Never put secrets in code, logs, tests or commits. Never read or print .env.
6. After every task run: pytest, ruff, mypy, vitest, tsc, oxlint. Do not say a task is done unless acceptance tests pass. If something could not be verified, say so plainly.
7. Small, reviewable commits with clear messages. No unrelated refactors.
8. Record any contract-breaking or architectural change in docs/decisions/ as an ADR.
9. Before coding, give a plan in 10 lines or fewer. After coding, give a summary in 10 lines or fewer: what changed, what passed, what is unverified, what is next.
10. Conserve credits: do not re-read the whole repo each time; open only the files you need.
```

## C2. Phase prompts

**Phase 0**

```
Task: Phase 0 from docs/BUILD_BRIEF.md.
(a) Update README.md and docs/architecture.md to the new scope (multi-domain, pack-based, realistic 3D, real execution). Add ADR 0005 "Domain-agnostic core with domain packs".
(b) Create tests/gold/ with a manifest format (paper id, expected domain tags, expected component list, evidence pointers). Do not commit PDFs.
(c) Add an evaluation command that runs extraction over the gold manifest and prints domain accuracy and component precision/recall.
Do not change product behaviour.
```

**Phase 1**

```
Task: Phase 1 from docs/BUILD_BRIEF.md, in this order, one commit each:
1. Postgres everywhere (keep Alembic). 2. S3-compatible object storage interface for PDFs/figures/artifacts. 3. A Modal-backed IsolationProvider for the existing execution service (network off by default, time and memory limits, ephemeral workspace, no secrets mounted); keep local_trusted tier fail-closed. 4. Durable job queue and worker. 5. Authentication plus project ownership checks on every endpoint. 6. CI workflow.
Acceptance: a run executes on Modal and its logs and artifacts appear through the existing run APIs; unauthenticated requests are rejected; CI is green.
```

**Phase 2**

```
Task: Phase 2 from docs/BUILD_BRIEF.md.
Define a Pack interface (detect, vocabulary, resolve_part, render_spec, simulators, preflight_rules, copilot_tools) with contract tests first. Replace the hard-coded PROFILES/domain handling with open-vocabulary domain tags on the graph. Move the existing electronics catalog and fixtures into an Electronics pack module. Add a toy-pack test proving a new pack registers with zero core changes. Grep must show no domain names left in core code.
```

**Phase 3**

```
Task: Phase 3 from docs/BUILD_BRIEF.md.
Extend ingestion to extract figures/diagram crops, equations and tables in an isolated worker. Add a vision-language extraction path through the provider interface (Baseten). Output domain tags, components, connections, parameters, evidence locators with confidence, and assumed flags. Cache by paper hash. Add UI to accept/edit/reject claims. Run the Phase 0 evaluation and report the numbers before and after.
```

**Phase 4**

```
Task: Phase 4 from docs/BUILD_BRIEF.md.
Build the asset registry (GLB model, footprint, pin map, license, source per part) and the resolver ladder (exact part, family/package, category) with confidence labels. Add procedural fallbacks for common packages. Replace box/cylinder/sphere node rendering in the 3D canvas with a GLB loader driven by pack render specs. Record the license of every asset; do not add assets whose license is unclear.
```

**Phase 5**

```
Task: Phase 5 from docs/BUILD_BRIEF.md.
Implement the Electronics pack: BOM/netlist from the graph, KiCad/Gerber import when provided, generated illustrative board layout otherwise, ngspice simulation adapter on Modal, electrical preflight, and a 3D board view with waveforms/voltages overlaid from measured runs. Validate on held-out electronics papers; never special-case a paper or a part. Acceptance: changing a component changes the measured output.
```

**Phase 6**

```
Task: Phase 6 from docs/BUILD_BRIEF.md.
Implement the ML/DL pack: allowlisted layer vocabulary, graph-to-PyTorch compiler from first-party templates only, training/eval on Modal with fixed seeds, tensor-shape preflight, and a 3D view with real tensor shapes and activation statistics. Acceptance: an edit changes the metric curve; an incompatible edit is rejected with a clear reason.
```

**Phases 7 and 8**

```
Task: Phase 7 (live telemetry over SSE/WebSocket, add/replace/remove components, baseline-vs-variant with paper-reported and measured numbers shown separately, measured/assumed/illustrative labels) then Phase 8 (LLM copilot with tools: read evidence, inspect graph and diffs, query runs, search parts, preflight, propose patches; human approval gate; citations in every answer; 30-question evaluation set). Follow docs/BUILD_BRIEF.md acceptance tests.
```

## C3. When Muse says "done"

Always ask: *"Show me the acceptance test output and list anything you did not verify."* Do not accept "done" without it.

---

# PART D: Decisions and risks

**Decisions needed from you**

1. **Test papers:** you will supply them later; the build must not depend on which ones they are. Collect at least 15 across 5 domains for Phase 0 and keep 5 as held-out.
2. **Credits:** confirm the unit and product of the 140 Muse credits (Model API balance or Muse Code usage), and check Baseten's balance. Modal's $100 is enough for small capped runs.
3. **Deadline:** any demo date? It decides how thin Phases 5 to 8 may be.

**Main risks**

- **Scope:** all domains at once will not finish. The pack interface is what makes "all domains" achievable over time.
- **Asset licensing:** reusing 3D models and part libraries requires correct attribution; track licenses from day one.
- **Extraction accuracy:** only measurable with the gold set; do not skip Phase 0.
- **Cost:** training and emulation on Modal can burn credits fast; enforce per-run caps and use small-scale runs.
- **Agent drift:** Muse previously drifted from the ViT scope to hardware catalogs. The master brief plus "one phase at a time" is the control.
