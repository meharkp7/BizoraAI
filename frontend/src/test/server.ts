import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import {
  adaptersFixture,
  comparisonFixture,
  componentDetailFixture,
  componentGenericFixture,
  componentSummaryFixture,
  copilotFixture,
  diffFixture,
  entitiesFixture,
  failedRun,
  graphFixture,
  layoutFixture,
  metricsFixture,
  notFound,
  paperExtractionFixture,
  parsedPaperFixture,
  preflightFixture,
  succeededRun,
  tableFixture,
  tableFixture2,
} from "./fixtures.ts";

export const handlers = [
  http.get("/health", () => HttpResponse.json({ status: "ok" })),

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
    return notFound("RESOURCE_NOT_FOUND", "Experiment run not found.");
  }),

  http.get("/api/v1/experiments/runs/:runId/metrics", ({ params }) =>
    params["runId"] === "run-ok" ? HttpResponse.json(metricsFixture) : HttpResponse.json([]),
  ),

  http.get("/api/v1/experiments/runs/:runId/artifacts", () => HttpResponse.json([])),

  http.get("/api/v1/experiments/comparisons", () => HttpResponse.json(comparisonFixture)),

  http.get("/api/v1/graphs/:projectId/:graphId/tables", ({ params }) => {
    if (params["projectId"] === "project-1" && params["graphId"] === "graph-1") {
      return HttpResponse.json([tableFixture, tableFixture2]);
    }
    return HttpResponse.json([]);
  }),

  http.post("/api/v1/papers/extract", () => HttpResponse.json(paperExtractionFixture, { status: 201 })),

  http.post("/api/v1/papers/parse", () => HttpResponse.json(parsedPaperFixture)),

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

  http.get("/api/v1/experiments/adapters", () => HttpResponse.json(adaptersFixture)),
];

export const server = setupServer(...handlers);
