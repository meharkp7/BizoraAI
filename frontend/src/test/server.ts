import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import {
  adaptersFixture,
  arenaFixture,
  authFixture,
  comparisonFixture,
  componentDetailFixture,
  componentGenericFixture,
  componentSummaryFixture,
  copilotFixture,
  copilotStreamBody,
  copilotThreadDetailFixture,
  copilotThreadFixture,
  diagramsFixture,
  diffFixture,
  entitiesFixture,
  failedRun,
  figuresFixture,
  graphFixture,
  graphSummariesFixture,
  layoutFixture,
  libraryFixture,
  memoryFixture,
  metricsFixture,
  notesFixture,
  notFound,
  paperExtractionFixture,
  paperImportFixture,
  paperTextFixture,
  parsedPaperFixture,
  qualitySummaryFixture,
  pendingRun,
  preflightFixture,
  renderSpecsFixture,
  reportedMetricsFixture,
  removalPreflightFixture,
  revisionHistoryFixture,
  runUsageFixture,
  samplePaperFixture,
  simulationPreviewFixture,
  succeededRun,
  tableFixture,
  tableFixture2,
  transplantFixture,
  usageSummaryFixture,
  whatIfFixture,
} from "./fixtures.ts";
import type { PaperNote } from "../lib/types.ts";

/** Mutable notes store for component tests; reset between tests. */
let notesStore: PaperNote[] = notesFixture.map((note) => ({ ...note }));
let nextNoteId = 100;

export function resetNotesStore(): void {
  notesStore = notesFixture.map((note) => ({ ...note }));
  nextNoteId = 100;
}

export const handlers = [
  http.get("/health", () => HttpResponse.json({ status: "ok" })),

  http.get("/api/v1/graphs", () => HttpResponse.json(graphSummariesFixture)),

  http.post("/api/v1/graphs/compare", () => HttpResponse.json(arenaFixture)),

  http.post(
    "/api/v1/graphs/:projectId/:graphId/transplant",
    () => HttpResponse.json(transplantFixture, { status: 201 }),
  ),

  http.get("/api/v1/projects/:projectId/memory", () => HttpResponse.json(memoryFixture)),

  http.post("/api/v1/projects/:projectId/memory", async ({ request, params }) => {
    const body = (await request.json()) as { fact: string; created_by: string };
    return HttpResponse.json(
      {
        id: 2,
        project_id: params["projectId"],
        fact: body.fact,
        created_by: body.created_by,
        created_at: "2026-11-02T00:00:00+00:00",
      },
      { status: 201 },
    );
  }),

  http.delete("/api/v1/projects/:projectId/memory/:factId", () => new HttpResponse(null, { status: 204 })),

  http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      const version = Number(params["version"]);
      if (version === 2) return HttpResponse.json(graphFixture);
      if (version === 1) return HttpResponse.json({ ...graphFixture, version: 1, parent_version: null });
    }
    return notFound("RESOURCE_NOT_FOUND", "Graph revision not found.");
  }),

  http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version/layout", ({ params }) => {
    if (
      params["projectId"] === "project-1" &&
      params["graphId"] === "graph-1" &&
      params["version"] === "2"
    ) {
      return HttpResponse.json(layoutFixture);
    }
    return notFound("RESOURCE_NOT_FOUND", "No layout was saved for this graph revision.");
  }),

  http.put("/api/v1/graphs/:projectId/:graphId/revisions/:version/layout", async ({ request }) => {
    const layout = (await request.json()) as typeof layoutFixture;
    return HttpResponse.json({ ...layout, updated_by: "test-user" });
  }),

  http.get("/api/v1/graphs/:projectId/:graphId/diff", () => HttpResponse.json(diffFixture)),

  http.post(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/nodes/:nodeId/removal-preflight",
    ({ params }) => {
      if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
        return HttpResponse.json({
          ...removalPreflightFixture,
          target_node_id: String(params["nodeId"]),
        });
      }
      return notFound("RESOURCE_NOT_FOUND", "Graph revision not found.");
    },
  ),

  http.get("/api/v1/graphs/:projectId/:graphId/revisions", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      return HttpResponse.json(revisionHistoryFixture);
    }
    return notFound("RESOURCE_NOT_FOUND", "Graph not found.");
  }),

  http.post(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/restore",
    ({ params }) => {
      if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
        return HttpResponse.json(
          { ...graphFixture, version: 3, parent_version: 2, created_by: "workspace-ui" },
          { status: 201 },
        );
      }
      return notFound("RESOURCE_NOT_FOUND", "Graph revision not found.");
    },
  ),

  http.get(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/entities",
    ({ params }) => {
      if (
        params["projectId"] === "project-1" &&
        params["graphId"] === "graph-1" &&
        params["version"] === "2"
      ) {
        return HttpResponse.json(entitiesFixture);
      }
      return notFound("RESOURCE_NOT_FOUND", "Graph revision not found.");
    },
  ),

  http.post("/api/v1/graphs/:projectId/:graphId/patches", async ({ request }) => {
    const patch = (await request.json()) as { base_version: number };
    return HttpResponse.json(
      { ...graphFixture, version: patch.base_version + 1, parent_version: patch.base_version },
      { status: 201 },
    );
  }),

  http.post("/api/v1/graphs/:projectId/:graphId/patch-batches", async ({ request }) => {
    const batch = (await request.json()) as { patches: { base_version: number }[] };
    const base = batch.patches[0]?.base_version ?? 1;
    return HttpResponse.json(
      { ...graphFixture, version: base + 1, parent_version: base },
      { status: 201 },
    );
  }),

  http.get("/api/v1/experiments/runs", () => HttpResponse.json([succeededRun, failedRun])),

  http.get("/api/v1/experiments/runs/:runId", ({ params }) => {
    if (params["runId"] === "run-ok") return HttpResponse.json(succeededRun);
    if (params["runId"] === "run-bad") return HttpResponse.json(failedRun);
    if (params["runId"] === "run-pending") return HttpResponse.json(pendingRun);
    return notFound("RESOURCE_NOT_FOUND", "Experiment run not found.");
  }),

  http.get("/api/v1/experiments/runs/:runId/metrics", ({ params }) =>
    params["runId"] === "run-ok" ? HttpResponse.json(metricsFixture) : HttpResponse.json([]),
  ),

  http.get("/api/v1/experiments/runs/:runId/artifacts", () => HttpResponse.json([])),

  http.get("/api/v1/experiments/comparisons", () => HttpResponse.json(comparisonFixture)),

  http.get("/api/v1/experiments/runs/:runId/reported-metrics", ({ request }) => {
    const url = new URL(request.url);
    const names = url.searchParams.getAll("names");
    return HttpResponse.json(
      reportedMetricsFixture.filter((entry) => names.includes(entry.name)),
    );
  }),

  http.get("/api/v1/graphs/:projectId/:graphId/tables", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      return HttpResponse.json([tableFixture, tableFixture2]);
    }
    return HttpResponse.json([]);
  }),

  http.get("/api/v1/graphs/:projectId/:graphId/figures", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      return HttpResponse.json(figuresFixture);
    }
    return HttpResponse.json([]);
  }),

  http.get("/api/v1/graphs/:projectId/:graphId/reported-metrics", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      return HttpResponse.json(reportedMetricsFixture);
    }
    return HttpResponse.json([]);
  }),

  http.post("/api/v1/papers/extract", () => HttpResponse.json(paperExtractionFixture, { status: 201 })),

  http.post("/api/v1/papers/parse", () => HttpResponse.json(parsedPaperFixture)),

  http.post("/api/v1/papers/import", () => HttpResponse.json(paperImportFixture, { status: 201 })),

  http.get("/api/v1/papers/sample", () => HttpResponse.json(samplePaperFixture)),

  http.get("/api/v1/quality/summary", () => HttpResponse.json(qualitySummaryFixture)),

  http.get("/api/v1/usage/summary", () => HttpResponse.json(usageSummaryFixture)),

  http.get("/api/v1/usage/runs", () => HttpResponse.json(runUsageFixture)),

  http.get("/api/v1/components", ({ request }) => {
    const url = new URL(request.url);
    const query = (url.searchParams.get("q") ?? "").toLowerCase();
    const generic = url.searchParams.get("generic");
    let entries = [componentSummaryFixture, componentGenericFixture];
    if (query !== "") {
      entries = entries.filter((entry) => entry.label.toLowerCase().includes(query));
    }
    if (generic === "true") entries = entries.filter((entry) => entry.generic);
    if (generic === "false") entries = entries.filter((entry) => !entry.generic);
    return HttpResponse.json(entries);
  }),

  http.get("/api/v1/components/:componentId", ({ params }) => {
    if (params["componentId"] === "npn-2n3904") {
      return HttpResponse.json(componentDetailFixture);
    }
    return notFound("RESOURCE_NOT_FOUND", "Component not found.");
  }),

  http.post(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/nodes/:nodeId/preflight",
    () => HttpResponse.json(preflightFixture),
  ),

  http.post("/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot", () =>
    HttpResponse.json(copilotFixture),
  ),

  http.get("/api/v1/graphs/:projectId/:graphId/copilot/threads", () =>
    HttpResponse.json([]),
  ),

  http.post("/api/v1/graphs/:projectId/:graphId/copilot/threads", () =>
    HttpResponse.json(copilotThreadFixture, { status: 201 }),
  ),

  http.get("/api/v1/graphs/:projectId/:graphId/copilot/threads/:threadId", () =>
    HttpResponse.json({ ...copilotThreadDetailFixture, turns: [] }),
  ),

  http.get("/api/v1/papers/:sourceId/text", () => HttpResponse.json(paperTextFixture)),

  http.post(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/copilot/stream",
    () =>
      new HttpResponse(copilotStreamBody(copilotFixture), {
        headers: { "Content-Type": "text/event-stream" },
      }),
  ),

  http.get("/api/v1/experiments/adapters", () => HttpResponse.json(adaptersFixture)),

  http.get(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/simulation-preview",
    () => HttpResponse.json(simulationPreviewFixture),
  ),

  http.get(
    "/api/v1/graphs/:projectId/:graphId/revisions/:version/render-specs",
    () => HttpResponse.json(renderSpecsFixture),
  ),

  http.get("/api/v1/papers/:paperId/diagrams", ({ params }) => {
    if (params["paperId"] === "paper-1") {
      return HttpResponse.json(diagramsFixture);
    }
    return notFound("RESOURCE_NOT_FOUND", "Paper not found.");
  }),

  http.post("/api/v1/papers/:paperId/whatif", async ({ params, request }) => {
    if (params["paperId"] !== "paper-1") {
      return notFound("RESOURCE_NOT_FOUND", "Paper not found.");
    }
    const body = (await request.json()) as { node_id?: unknown; params?: unknown };
    if (typeof body.node_id !== "string" || typeof body.params !== "object") {
      return HttpResponse.json({ detail: "Bad request." }, { status: 400 });
    }
    return HttpResponse.json({
      ...whatIfFixture,
      node_id: body.node_id,
      params_applied: body.params,
    });
  }),

  http.post("/api/v1/papers/:paperId/whatif/parse", async ({ params, request }) => {
    if (params["paperId"] !== "paper-1") {
      return notFound("RESOURCE_NOT_FOUND", "Paper not found.");
    }
    const body = (await request.json()) as { text?: unknown; node_id?: unknown };
    if (typeof body.text !== "string" || body.text.trim() === "") {
      return HttpResponse.json({ detail: "Bad request." }, { status: 400 });
    }
    const nodeId = typeof body.node_id === "string" ? body.node_id : "fabricate";
    const match = body.text.match(/cell_count\D*(\d+)/i);
    return HttpResponse.json({
      node_id: nodeId,
      node_label: "Fabricate array",
      params: match ? { cell_count: match[1] } : {},
    });
  }),

  http.post("/api/v1/auth/register", async ({ request }) => {
    const body = (await request.json()) as { email?: unknown; password?: unknown };
    if (typeof body.email !== "string" || typeof body.password !== "string") {
      return HttpResponse.json({ detail: "Bad request." }, { status: 400 });
    }
    return HttpResponse.json(authFixture, { status: 201 });
  }),

  http.post("/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email?: unknown; password?: unknown };
    if (body.email === "ghost@example.com") {
      return HttpResponse.json({ detail: "Invalid email or password." }, { status: 401 });
    }
    if (typeof body.email !== "string" || typeof body.password !== "string") {
      return HttpResponse.json({ detail: "Bad request." }, { status: 400 });
    }
    return HttpResponse.json(authFixture);
  }),

  http.get("/api/v1/auth/me", ({ request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    return HttpResponse.json(authFixture.user);
  }),

  http.get("/api/v1/users/me/papers", ({ request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    return HttpResponse.json(libraryFixture);
  }),

  http.get("/api/v1/papers/:paperId/notes", ({ params, request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    return HttpResponse.json(
      notesStore.filter((note) => note.paper_id === params["paperId"]),
    );
  }),

  http.post("/api/v1/papers/:paperId/notes", async ({ params, request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    const body = (await request.json()) as { body?: unknown };
    if (typeof body.body !== "string" || body.body.trim() === "") {
      return HttpResponse.json({ detail: "Note body must be non-empty." }, { status: 422 });
    }
    const note = {
      id: nextNoteId++,
      paper_id: params["paperId"] as string,
      body: body.body.trim(),
      created_at: "2026-01-04T00:00:00+00:00",
      updated_at: "2026-01-04T00:00:00+00:00",
    };
    notesStore.push(note);
    return HttpResponse.json(note, { status: 201 });
  }),

  http.put("/api/v1/papers/:paperId/notes/:noteId", async ({ params, request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    const note = notesStore.find((candidate) => candidate.id === Number(params["noteId"]));
    if (!note || note.paper_id !== params["paperId"]) {
      return notFound("RESOURCE_NOT_FOUND", "Note not found.");
    }
    const body = (await request.json()) as { body?: unknown };
    if (typeof body.body !== "string" || body.body.trim() === "") {
      return HttpResponse.json({ detail: "Note body must be non-empty." }, { status: 422 });
    }
    note.body = body.body.trim();
    return HttpResponse.json(note);
  }),

  http.delete("/api/v1/papers/:paperId/notes/:noteId", ({ params, request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Authentication required." }, { status: 401 });
    }
    const index = notesStore.findIndex((candidate) => candidate.id === Number(params["noteId"]));
    if (index < 0 || notesStore[index].paper_id !== params["paperId"]) {
      return notFound("RESOURCE_NOT_FOUND", "Note not found.");
    }
    notesStore.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
];

export const server = setupServer(...handlers);
