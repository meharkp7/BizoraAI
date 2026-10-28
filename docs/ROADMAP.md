# BizoraAI Roadmap (from Phase 0)

Source of truth for scope and acceptance tests: `docs/BUILD_BRIEF.md`. This file tracks phase status, open user decisions, conflict dispositions, risks, and gate criteria. Written at the end of Phase 0 (28 Oct 2026).

## Phase status

| Phase | Brief scope | Status | Evidence / gate output |
| --- | --- | --- | --- |
| 0 — Reset and baseline | Docs to scope, ADR 0005, gold manifest format, eval command, no behavior change | Done except user steps (papers + commit) | pytest 548 passed; ruff clean; mypy strict clean (61 files); tsc clean; oxlint 0 errors (1 pre-existing warning); vitest 93 passed; `python -m bizora.eval_gold` exits 0 with honest empty-manifest zeros |
| 1 — Platform hardening | Postgres, object storage, Modal executor, job queue, auth, CI | Not started | Gate: run executes on Modal with logs/artifacts in UI; unauthenticated requests rejected; CI green |
| 2 — Domain-agnostic core | Pack interface + contract tests, open-vocab domain tags, Electronics pack split, toy-pack test | Not started | Gate: no domain names in core code (grep); toy pack registers with zero core changes |
| 3 — Extraction v2 | Vision ingestion, Muse Spark 1.3 Responses API path, assumed flags, correction UI, cache | Not started | Gate: `make eval` meets R1–R3 targets on gold set |
| 4 — Part resolver + 3D assets | Asset registry, resolver ladder, procedural fallbacks, GLB loader | Not started | Gate: R5 passes on ESP32 demo paper |
| 5 — Electronics pack | Netlist/BOM, KiCad import, board gen, ngspice on Modal, electrical preflight | Not started | Gate: held-out paper shows board + simulation; component change changes measured output |
| 6 — ML/DL pack | Layer vocab, PyTorch compiler, Modal training, shape preflight | Not started | Gate: edit changes metric curve; incompatible edit rejected |
| 7 — Workspace + telemetry | SSE/WebSocket stream, add/replace/remove, baseline-vs-variant | Not started | Gate: R7 + R8 pass |
| 8 — LLM copilot | Tool-using copilot, approval gate, 30-question eval | Not started | Gate: R9 passes (85% cited, zero unapproved writes) |
| 9 — More packs | IoT, robotics, mechanical | Not started | Per-pack gold papers + acceptance tests |
| 10 — Production release | Observability, load/abuse, security review, cost caps, runbook | Not started | Release checklist in brief Part B |

Suggested order per brief: 0, then 1+2, then 3, 4, 5+6 in parallel, 7, 8, 9, 10. If credits run short, protect 0, 2, 3, 4, 5, 6, 7, 8.

## Critic verdicts vs Phase 0 implementation — dispositions

The product critic reviewed 7 areas against brief Part A. Phase 0's mandate was docs + gold set + eval harness with no behavior change, so all verdicts below are dispositions, not Phase 0 code changes:

1. Paper upload/extraction (REWORK: text-only, lexical domains, no eval) — ADOPTED as plan. Phase 0 delivered the eval harness and gold-manifest format; vision path, model domain tags, and assumed flags are scheduled for Phase 3. Paper-agnostic upload and no-invent prompting kept as critic directed.
2. 2D editing (KEEP) — HONORED. No patch/version/canvas code touched; `git status` confirms docs + new files only.
3. 3D archetype explorer (REJECT as appearance-only) — ADOPTED as plan. Rebuild on pack render specs + GLB loader scheduled for Phase 4; orbit/selection shell may be reused.
4. Component library + preflight (REWORK: PROFILES coupling, thin rules) — ADOPTED as plan. Catalog-to-pack move and PROFILES decoupling scheduled for Phase 2; real rules for Phases 5–6.
5. Deterministic copilot (REWORK: needs LLM + tools + eval) — ADOPTED as plan. Approval-gate UX kept; LLM brain scheduled for Phase 8 (regex stays as fast path).
6. Deterministic-test runs (KEEP as validation harness) — HONORED. Lease/registry/isolation infra untouched; Modal/ngspice adapters scheduled for Phases 1/5/6.
7. Comparison (KEEP; add paper-reported numbers alongside measured) — HONORED with note. Comparison service untouched; TablesPage gap is a small Phase 7 addition.
8. Falsification (a): UI claim "Any research PDF works" (`HomePage.tsx`) is unverified — NOTED, not fixed. Phase 0 must not change product behavior; claim stays flagged until R1–R3 pass in Phase 3.
9. Falsification (b): hard-coded `PROFILES` + domain mirrors must go — ADOPTED as plan. Removal is Phase 2's core task (grep gate).
10. Falsification (c): RunPanel honesty wording confirmed genuine — HONORED. Wording untouched.

No critic verdict required a Phase 0 behavior change, so there are no unresolved critic/implementation conflicts. The one cross-report conflict was the PDF gitignore rule: early reports said `.gitignore` had no gold-PDF rule and the user must add one, but a later change added `tests/gold/papers/*` + `!tests/gold/papers/.gitkeep` (verified live: probe PDF invisible to git, manifest/README/`.gitkeep` tracked). Disposition: RESOLVED in working tree, awaiting user commit (see decision 2).

## Decisions needed from the user (brief Part D + Phase 0)

1. **Test papers (brief D1).** Supply at least 15 papers across 5+ domains (brief suggests ESP32/IoT system, analog/power circuit with PCB, ViT, CNN, robot-arm controller, quantization paper). For each, the manifest needs expected domain tags, component list, and evidence pointers — see `tests/gold/README.md`. Keep at least 5 papers held-out (never used while building, only for testing). Respect paper licenses.
2. **PDF gitignore rule (Phase 0 outcome — confirm, don't author).** The working tree already ignores gold PDFs via `tests/gold/papers/*` + `!tests/gold/papers/.gitkeep` in `.gitignore` (uncommitted). Confirm this local-only choice by committing it as-is, or say if you prefer a different rule (e.g. global `*.pdf`) before placing any PDFs. Do not place PDFs until this is committed.
3. **Credits and billing (brief D2).** Confirm the unit/product of the ~140 Muse credits (Model API balance vs Muse Code plan usage — billed separately; run `muse usage` and open the Billing page, noting the earlier billing restriction), check the Baseten balance (usage not visible in dashboard; plan without it until confirmed), and confirm Modal's $100. Set Modal per-run time/GPU caps and a spend alert well below $100 before Phase 1.
4. **Commit Phase 0 (brief Phase 0 step 1).** Agents were forbidden from committing. Review the working tree (modified: `.gitignore`, `README.md`, `docs/architecture.md`; new: ADR 0005, gold contract, eval command, `tests/gold/`, 2 test files), then commit or stash. Also rotate the Baseten key if the zip was ever shared, and confirm via `git log --all -- .env` that no key was committed.
5. **Deadline (brief D3).** Any demo date? It decides how thin Phases 5–8 may be.

## Risks (brief Part D, updated for Phase 0)

- **Scope:** all domains at once will not finish; the pack interface (Phase 2) is what makes generality achievable over time.
- **Asset licensing:** track licenses/attribution for every 3D model and part library from day one (matters from Phase 4).
- **Extraction accuracy:** still unmeasurable — the manifest ships with zero papers. Do not skip supplying the gold set.
- **Cost:** Modal training/emulation can burn credits fast; per-run caps + small runs + paper-hash caching (Phase 3).
- **Agent drift:** previous drift from ViT scope to hardware catalogs; control is master brief + one phase at a time + held-out acceptance.
- **Phase 0 residue:** uncommitted tree (user must commit); `--provider baseten` eval path never exercised live (needs credentials/network).

## Next-gate criteria (entering Phase 1)

Phase 0 is fully done when the user has: (1) committed the working tree including the `.gitignore` PDF rule; (2) supplied ≥15 gold papers with manifest entries (5 held-out); (3) confirmed credits/billing per decision 3. Then `python -m bizora.eval_gold` should print nonzero baseline numbers (domain accuracy, component precision/recall) instead of the current honest zeros. Phase 1 starts only after that report is reviewed ("continue" per brief C0).
