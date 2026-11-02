# SRAM PUF diagram-integration screenshots (uncommitted)

Paper: Shifman et al., 2-bit/cell tilting SRAM PUF (`09246212`,
source `paper-4c144156`). No fixtures in product code.

## How the shots were captured

The sandbox blocks TCP binds, so no live servers back these shots.
Instead the production bundle is served from disk and the REAL backend
payloads are fulfilled at the network layer (`/tmp/sram-demo/probe.mjs`):
the diagrams/figures/what-if responses are dumped in-process from the
demo backend (seeded `/tmp` sqlite DB + live v3 provider cache, prompt
version 3, Muse provider), byte-identical to what the endpoints serve.
Only the workspace shell around the diagram tabs (graph revision,
entities, adapters) is stubbed.

## How the demo backend was fed

The demo backend ran a **live end-to-end extraction** through the real
`GET /papers/{id}/diagrams` endpoint (prompt version 3) with the Muse
provider:

- Demo DB is a `/tmp` copy of `bizora_run.db` with three figure records
  inserted (real image bytes from the eval dir) plus the real paper text
  (13 pages, `[Page N]` markers) persisted via the new `paper_texts`
  table, exactly as ingest now stores it.
- Demo cache (`BIZORA_CACHE_DIR` under `/tmp`) holds live provider
  output, re-rolled until correct; the served state is:
  - `sram-bitcell-fig1` -> circuit, 10 components, 10 placed,
    zero validation errors, 10/10 with figure evidence. All
    orientations match the paper, including the left inverter at
    rot180 (apex-left, bubble-right; verified against an enlarged
    crop of the figure).
  - `sram-die-photo` -> structure **rejected by validation**
    (array root with a bare count of 2000, no rows/cols grid, no
    sibling blocks — cannot render honestly). The endpoint serves the
    **text-derived** structure instead (test die + 2-bit and 1-bit
    arrays, serial readout, shared OR gate); the figure error is
    preserved in `validation`.
  - `sram-hd-plot` -> kind `other`, no IR. Faithful: plots yield nothing.
  - Methodology: no flow figure exists, so the endpoint serves the
    **text-derived** methodology — 9 nodes in 4 groups with page/quote
    evidence, every node carrying its stated settings in `params`
    (prompt v3; e.g. `array_cells: 2000` on the measurement step).
- Served structures pass through `normalize_structure_layout`: shared
  blocks nested under an array move to chip level and unplaced blocks
  take distinct illustrative sides, each adjustment surfaced as a
  validation warning in the UI. Deterministic — no re-extraction,
  cache untouched.
- The 3D tab opens on the Circuit 3D scene derived client-side from
  the served circuit IR (one part per component, figure evidence
  carried over), each part dressed with its standard textbook
  structure by component type, plus a rat's-nest of lifted wire arcs
  joining the parts each net touches (supply red, ground slate,
  signal copper). Nothing is paper-specific: the derivation, the
  wire router, the layout repair, and the type models are generic
  over any paper's IRs.
- The cell interior dresses the parts that name a known device
  (typed `part` or whole-word label keywords): NMOS/PMOS pairs build
  as twin FET stacks, the MOM unit as stacked plates. Switches and
  keepers name no device, so they honestly stay boxes; the caption
  says which is which.
- The full structure was checked and is correct: a test-chip die
  carrying the 5x32-of-5x400 representative cell grid plus readout
  and OR gate, illustrative placements disclosed. The die plate now
  wears a silicon finish (app-layer, any `chip` block) so it reads
  as a die instead of a PCB.
- Methodology edges that stop at dagre's node rectangle instead of the
  drawn diamond are bridged to the diamond border in the app layer
  (the engine stays byte-identical): the fit matches the engine's real
  `class="edge "` tags, so both diamond legs now connect visibly.
- Methodology nodes with stated settings carry a ± badge (9/9 here,
  rect/diamond/path outlines all covered); clicking one opens the
  Inspector's what-if editor for that step.
- The signal-flow pulse flies along the drawn wires at 300 px/s: the
  router densifies long runs, bridges symbol-cut islands through
  device bodies, and always leaves from the nearest connected copper
  (snap-first, pin-scale window), so 8 of the 10 legs ride copper
  and the 2 across genuinely separate nets fade honestly. The tag
  riding the dot names the step, the from → to leg, the shared net,
  and the paper's own quote about the stop.
- The what-if editor (`POST /papers/{id}/whatif`) estimates outcomes
  from the paper's own numbers with cited quotes; estimates are
  labeled as such and never presented as measurements.

`schematic-illustrative.png` strips component placement from the served
payload (via request interception at capture time; the cache is
untouched) to show the auto-layout badge, a real state for papers
whose extraction carries no placement.

Seed scripts live in `/tmp/sram-demo/` (scratch, not in the repo).
The methodology/schematic/structure failure fallbacks (paper figure +
reason, never a placeholder) are covered by unit tests and
`e2e/diagrams.spec.ts` with a stubbed endpoint.

## Shots

- `methodology.png` — 9-node paper flow in 4 groups, vertical by
  default so every node renders at full text size (Horizontal one
  click away), stated settings printed on each node, ± what-if
  badges on all 9.
- `methodology-inspector.png` — clicked measurement step: quote
  evidence plus the what-if editor with its stated settings.
- `methodology-whatif.png` — what-if outcome for 5000 cells: scaled
  estimate with cited paper numbers, assumptions, and the
  not-a-measurement label.
- `schematic.png` — engine schematic with the signal-flow walkthrough
  (Step 3 of 10); the pulse rides the wire into S1 with its 4-line
  tag (step, K2 → S1, via En, paper quote), and labels carry a
  background halo so wires never swallow text.
- `schematic-inspector.png` — clicked K1 with figure evidence.
- `schematic-illustrative.png` — auto-layout badge (placement stripped).
- `structure-3d.png` — the default 3D scene (Circuit 3D): the ten
  schematic components as textbook structures (NMOS/PMOS with
  diffusions and poly gates, combined inverters, tapered ground),
  derived from the circuit IR (no board), joined by the net
  rat's-nest.
- `structure-spotlight.png` — picked S1 from the parts list: it glows
  while the rest dims to ghosts, Inspector open with its evidence.
- `structure-hover.png` — hover tooltip naming the part under the cursor.
- `structure-full.png` — full chip via `sceneToThree`: both arrays plus
  readout and OR gate, with the arrangement warning shown.
- `structure-inspector.png` — clicked array cell with page evidence.
- `structure-detail.png` — cell interior: the extracted parts inside
  one 2-bit cell, NMOS/PMOS pairs and the MOM capacitor dressed,
  switches/keepers as honest boxes.
- `live-trial-render.png` — library "Try in schematic": a 1N4148 diode
  auditioned below the paper circuit as a dashed assumed part with
  open pin stubs, value read from the catalog (0.7 V). Captured live
  against the user's own servers.
- `live-bot-moved.png` — the copilot robot's chat overlay mid-drag,
  with a real grounded reply (paper evidence cards). Captured live
  against the user's own servers.
- `structure-detail-inspector.png` — clicked NMOS pair with quote evidence.

## Phase 6 addendum (prompt v4, true component geometry)

- Structure prompts (figure + text) now ask for the repeated cell's
  internal devices as children with typed `part`; prompt version
  bumped 3 -> 4 (old cache entries stay valid under their own keys).
- New graft: when a figure structure's repeated cell is bare but the
  paper text states its devices, the text children (with their own
  page/quote evidence) are grafted into the figure cell, disclosed
  via `sources["structure:cell-interior"] = "text"` plus a validation
  warning. SRAM serves 12 typed cell devices again (N1-N4, P1-P2,
  S1-S3, K1-K2, coupling capacitor); the Cell interior tab is back.
- Frontend: `componentModels.ts` restores the textbook NMOS/PMOS,
  pair, inverter, R/C/L and ground builders and adds diode, sources,
  buffer, QFP amp/comparator, ADC/DAC steps, finned sensor, banded
  database, weight-layer stacks, I/O funnels, decision diamond, and
  module slabs. Mapping is typed `part`/`kind` first, whole device
  words only when the part is untyped; typed blocks keep the honest
  labeled plate. Verified in headless Chrome against the real SRAM
  payload (`/tmp/phase6-shots/`, uncommitted): full structure,
  circuit 3D, cell interior, and a builder gallery from every angle.
