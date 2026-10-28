# ADR 0005: Domain-agnostic core with domain packs

- **Status:** Accepted
- **Decision:** The core (graph, evidence, versions, patches, runs,
  comparison, copilot) is domain-agnostic and names no domain, part, or
  paper. Every domain ships as a **pack** behind a stable Pack interface
  (`detect`, `vocabulary`, `resolve_part`, `render_spec`, `simulators`,
  `preflight_rules`, `copilot_tools`). Domains are open-vocabulary,
  multi-label tags the model produces at extraction time; routing picks
  the best-matching pack or falls back to explore-only mode. Launch
  packs are ML/DL and Electronics.
- **Context:** The product must serve any technical domain, but domains
  differ in vocabulary, parts, rendering, simulation, and compatibility
  rules. The current codebase answers domain questions with a hard-coded
  lexical table in core code, which cannot generalize and violates Rule
  Zero (see `docs/BUILD_BRIEF.md`). ML/DL and Electronics are the most
  different pair, so one core serving both proves the generality
  mechanism for later packs (IoT, robotics, mechanical).
- **Consequences:** New domains arrive as new pack modules with zero
  core changes, proven by a toy-pack registration test. The existing
  hard-coded domain table and electronics catalog move into the
  Electronics pack as data. Core code must never branch on domain names,
  paper titles, or part names; grep for domain names in core is a
  review gate.
- **Guardrails:** Rule Zero stays in force: test papers measure quality
  but never special-case code; unknown extractions return *assumed* or
  *unsupported* with a reason. Pack code holds data and rules, never
  secrets; execution still goes only through allowlisted adapters on
  isolated compute.
