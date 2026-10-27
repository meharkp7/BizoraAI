import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { BizoraApiError, api } from "./api.ts";
import { server } from "../test/server.ts";
import { layoutFixture } from "../test/fixtures.ts";

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    const health = await api.health();
    expect(health).toEqual({ status: "ok" });
  });

  it("fetches a graph revision", async () => {
    const graph = await api.getGraphRevision("project-1", "graph-1", 2);
    expect(graph.title).toBe("Vision transformer");
    expect(graph.nodes).toHaveLength(2);
  });

  it("raises a typed error with code and details on API failures", async () => {
    const error = await api.getGraphRevision("missing", "missing", 1).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(BizoraApiError);
    const apiError = error as BizoraApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.code).toBe("RESOURCE_NOT_FOUND");
    expect(apiError.isNotFound).toBe(true);
    expect(apiError.isConflict).toBe(false);
  });

  it("reports unreachable hosts distinctly", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", () =>
        HttpResponse.error(),
      ),
    );
    const error = await api.getGraphRevision("project-1", "graph-1", 2).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(BizoraApiError);
    expect((error as BizoraApiError).code).toBe("NETWORK_UNREACHABLE");
    expect((error as BizoraApiError).status).toBe(0);
  });

  it("surfaces plain FastAPI detail errors", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", () =>
        HttpResponse.json({ detail: "Graph revision not found." }, { status: 404 }),
      ),
    );
    const error = await api.getGraphRevision("demo", "vit", 9).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(BizoraApiError);
    const apiError = error as BizoraApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.code).toBe("RESOURCE_NOT_FOUND");
    expect(apiError.message).toBe("Graph revision not found.");
    expect(apiError.isNotFound).toBe(true);
  });

  it("rejects non-JSON failures without crashing", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/revisions/:version", () =>
        new HttpResponse("gateway exploded", { status: 502 }),
      ),
    );
    const error = await api.getGraphRevision("project-1", "graph-1", 2).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(BizoraApiError);
    expect((error as BizoraApiError).code).toBe("UNEXPECTED_RESPONSE");
  });

  it("round-trips a layout save", async () => {
    const saved = await api.saveLayout(layoutFixture);
    expect(saved.updated_by).toBe("test-user");
    expect(saved.positions).toHaveLength(1);
  });
});
