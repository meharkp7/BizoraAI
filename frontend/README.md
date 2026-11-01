# Bizora frontend (Phase D foundation)

React + TypeScript + Vite single-page app: routing, workspace shell, theme
system, typed API client with a TanStack Query layer, inspector/evidence
panels, loading/error/empty states, and the Vitest + Playwright harnesses.
The workspace canvas shows three diagram views (Methodology, Schematic, 3D)
rendered by the vendored diagram engine from `GET /papers/{id}/diagrams`;
when the engine refuses an IR, the canvas falls back to the paper's own
figure with clickable overlays, never a placeholder diagram. Methodology
nodes carry editable settings with a what-if estimate behind them
(`POST /papers/{id}/whatif`, labeled as an estimate); the schematic has
a wire-following walkthrough with per-leg explainer tags; 3D opens on
the circuit build with a parts list, spotlight, and hover naming.

## Prerequisites

- Node 20+
- The Bizora backend API (dev proxy forwards `/api` and `/health`)

## Run

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in a browser. Start the backend first so the
workspace can load real revisions:

```bash
# repository root
python -m uvicorn bizora.main:app --port 8000
```

If the API is served elsewhere, set `VITE_API_BASE_URL` (same-origin path or
absolute URL) in `frontend/.env.local`.

> Note: npm 10.8.x crashes resolving this tree (`edgesOut` arborist bug). If
> `npm install` fails that way, retry with `npm install --legacy-peer-deps`.

## Checks

```bash
npm run build    # strict tsc + production bundle
npm run lint     # oxlint
npm run test     # vitest unit suite (MSW-mocked API)
npm run test:e2e # Playwright smoke (spins up vite dev; API stubbed)
```

`npm run test:e2e` needs the Playwright chromium browser once:

```bash
npx playwright install chromium
```

## Structure

- `src/lib/types.ts` — API contract types mirroring `src/bizora/contracts`
- `src/lib/api.ts` — typed fetch client with `BizoraApiError`
- `src/lib/store.ts` — zustand UI store: theme + shared 2D/3D selection
- `src/app/queries.ts` — TanStack Query hooks; `src/app/routes.tsx` — routes
- `src/components/` — app shell, theme toggle, loading/error/empty states
- `src/features/` — home, workspace (revision viewer, inspector, evidence,
  diff), diagrams (Methodology/Schematic/3D views), runs, comparison
- `src/diagram-engine/` — vendored renderer (byte-identical to
  `bizora-diagram-engine.zip`); checked under `tsconfig.engine.json`
- `src/test/` — MSW handlers/fixtures shared by unit tests
- `e2e/` — Playwright smoke specs (network-stubbed; seeded-API E2E is Phase I)
