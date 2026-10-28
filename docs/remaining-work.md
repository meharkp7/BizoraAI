# Remaining work checklist — component workflow

Status as of the live demonstrations in this session. Every item below
names its dependencies, acceptance criteria, and demo status. Nothing
here is claimed as done without the cited evidence.

## Live-demonstrated (running UI, real backend, Postgres)

Demonstrated in Chrome against `vite dev` + `uvicorn` + Postgres; each
flow drove the actual UI and persisted real revisions and runs.

- SRAM/electronics: searched the library for 2N3904, inspected specs /
  pinout / interfaces / evidence, validated the swap against the
  access-transistors node, applied it as fixture-sram v2, and executed a
  deterministic validation run to SUCCEEDED with a persisted run record.
- IoT: opened the fixture-iot workspace, replaced the temperature sensor
  with a BME280, configured I2C address and sample period through schema
  fields, validated interfaces, and saved v2 with the configuration
  visible in the inspector.
- LLM quantization: replaced NF4 with FP16 on fixture-quant, inspected
  the updated configuration, ran v2 to SUCCEEDED, and used the copilot
  to compare NF4 vs FP16 with a spec table.
- Speech/signal: replaced the QPSK modulator with a PSK stage
  (fixture-signal v2), then applied a copilot-proposed configuration
  change (modulation order) as v3; the 2D pipeline shows the new stage.
- Software architecture: replaced the storage node with PostgreSQL 16
  (fixture-distributed v2) with two preserved connections shown; an
  incompatible worker-to-MQTT swap was rejected in the preview (Apply
  disabled) and rejected again at the patch layer (422).
- Entities failure mode: with `/entities` failing, the UI now shows an
  explicit warning in the heading and the 3D view instead of silently
  rendering generic markers.

## Test-only (covered by suite, not live-demoed)

- Catalog integrity: 58 entries link to real registry domains/entity
  types; exact parts carry part numbers; node kinds validate
  (`tests/unit/test_component_library.py`).
- Preflight edge cases: cross-domain warnings, unknown config keys,
  supply-range warnings, invalid enum rejection
  (`tests/unit/test_component_library.py`, `test_components_api.py`).
- Copilot intents: find/compare/replace/config/status/run-explain,
  including incompatible-swap refusal without a proposal
  (`tests/unit/test_component_library.py`).
- Frontend units (93 vitest) and stubbed Playwright specs (17 total,
  including the new `e2e/library.spec.ts`).

## Partially implemented

- Reference verification: 7 catalog references ship with verified URLs
  (4 TI product pages, Arduino Uno docs, Postgres docs, Kafka docs).
  Remaining exact parts show manufacturer + part number with an explicit
  "not verified" note. Acceptance: every exact part links a manufacturer
  page that returns HTTP 200; re-run the URL check before release.
- Pinout coverage: pinouts exist for parts with stable public pinouts;
  generics and software entities carry none. Acceptance: any part shown
  with a pin diagram cites its source drawing.
- Run diagnostics: the deterministic adapter computes diagnostics
  (node/edge counts, checksum, seed) but the execution service does not
  persist them, so the run page shows the run record + status + metrics
  but no log lines. Acceptance: diagnostics persisted per run and
  rendered in a log section.

## Unsupported (explicitly reported in the UI)

- Domain simulators: SPICE-class circuit simulation,
  hardware-in-the-loop, and LLM inference have no registered adapter.
  The run panel and the copilot both say so; runs perform genuine
  deterministic validation only.
- LLM-backed copilot: the copilot is a deterministic intent engine over
  the catalog and graph state. Free-form questions outside its intents
  fall back to library search or help text.
- Deep-learning catalog entries: the architecture supports the domain
  but no entries are seeded yet.

## Remaining work

1. Persist run diagnostics.
   Dependencies: execution service, run contracts, Alembic migration.
   Acceptance: a succeeded run shows its adapter log lines; migration
   applies to the existing database without data loss. Demo: run detail
   page shows the validation log.
2. Verify remaining datasheet/reference URLs from an unrestricted
   network (onsemi, Infineon, Espressif, Bosch, arxiv, bitsandbytes).
   Dependencies: none. Acceptance: each new URL returns HTTP 200 and
   the page title names the part; unverified entries stay unlabeled.
3. Seed deep-learning catalog entries (embedding/attention/optimizer
   blocks) once a demo graph needs them.
   Dependencies: none. Acceptance: catalog tests pass; entries appear
   in library search.
4. Add a SPICE-class adapter (e.g. ngspice-backed) for electronics
   graphs behind the adapter registry with isolation review.
   Dependencies: adapter interface, sandboxing decision, docs/security
   update. Acceptance: an SRAM revision runs end-to-end and reports
   measured metrics with `measured` result kind. Demo: run detail page.
5. Validate UPDATE_NODE_CONFIG payloads against the component config
   schema when the node carries a catalog identity.
   Dependencies: node-to-component linkage on replacement. Acceptance:
   out-of-schema values are rejected with field-level errors.
6. LLM-backed copilot explanations via the existing Baseten provider,
   with the deterministic engine as fallback and all proposals still
   approval-gated.
   Dependencies: provider availability, prompt-injection review.
   Acceptance: offline fallback behaves exactly as today; online
   answers cite catalog entries.
7. Paper-graph entity coverage: most extracted-paper nodes resolve
   generic (honest placeholders). Extend registry vocabulary per
   domain as new papers arrive.
   Dependencies: per-paper review; never fabricate parts. Acceptance:
   new resolutions cite matched terms; existing fixture resolutions
   unchanged.
