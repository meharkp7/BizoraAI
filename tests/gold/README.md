# Gold set manifest

The gold set measures extraction quality on real papers. Target (brief R1-R3):
at least 15 papers across at least 5 domains; keep at least 5 papers aside
as held-out (never used while building, only to test).

## Adding a paper

1. Place the PDF under `tests/gold/papers/` (create the directory if needed),
   or reference the user-supplied corpus under `research_papers/`.
   **Never commit PDFs** — both locations are git-ignored; keep them local only.
2. Add one entry to `manifest.json` (set `held_out: true` for the reserved
   test-only papers):

```json
{
  "paper_id": "esp32-soil-monitor",
  "pdf_path": "tests/gold/papers/esp32-soil-monitor.pdf",
  "domain_tags": ["embedded IoT", "sensor system"],
  "components": [
    {
      "name": "ESP32 DevKit",
      "aliases": ["ESP32"],
      "evidence": [{"kind": "figure", "locator": "Fig. 2"}]
    }
  ],
  "evidence": [{"kind": "page", "locator": "p.3"}]
}
```

Rules:

- `paper_id`: lowercase slug, unique in the manifest.
- `pdf_path`: repo-relative path to the `.pdf`, no `..`, no absolute paths.
- `domain_tags`: open-vocabulary labels, **primary first**.
- `components`: hand-checked expected components; `aliases` are accepted
  name variants; `evidence` kinds are `page`, `figure`, `equation`,
  `table`, `quote`, or `url`.
- Respect paper licenses. Test papers are inputs for measuring quality,
  never special cases in code (Rule Zero).

## Running the evaluation

```sh
python -m bizora.eval_gold
python -m bizora.eval_gold --provider muse --split dev
python -m bizora.eval_gold --provider muse --split heldout
```

The command prints per-paper outcomes plus domain accuracy and component
precision/recall. Missing PDFs report as `MISSING` without crashing. With
zero papers it prints honest zeros plus `awaiting gold papers`.

Scoring: domain matches on normalized equality with any tag; a component
matches when a gold name/alias equals a predicted label after
normalization, or one side's tokens contain the other's (so terse gold
names match descriptive predicted labels). Single generic tokens can
over-match; every provider faces the same scorer, so comparisons stay
fair. Known limitation: no stemming or synonym handling, so
"aging classification" will not match "aged chip classification" —
use aliases for genuine paper-term variants.

Draft graphs cache by provider and PDF hash under `tests/gold/.cache/`
(git-ignored); re-runs are free unless `--refresh` is passed. Metered
providers print a `tokens_input/tokens_output/live_calls` line. The Muse
provider reads `MUSE_API_KEY` from the environment (`/Users/meharkapoor7/BizoraAI/.env`
supplies it locally; never print or commit it).
