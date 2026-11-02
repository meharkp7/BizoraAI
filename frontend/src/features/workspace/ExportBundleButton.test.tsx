import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../../test/server.ts";
import { ExportBundleButton } from "./ExportBundleButton.tsx";

const BUNDLE = {
  bundle_version: "1.0",
  exported_at: "2026-11-02T00:00:00+00:00",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  graph: {
    schema_version: "1.0",
    project_id: "project-1",
    graph_id: "graph-1",
    version: 2,
    title: "Vision transformer",
    source_ids: [],
    nodes: [],
    edges: [],
    created_by: "tester",
  },
  memory: [],
};

describe("ExportBundleButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("downloads the bundle as a JSON file", async () => {
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/export", () =>
        HttpResponse.json(BUNDLE),
      ),
    );
    const created: string[] = [];
    vi.stubGlobal(
      "URL",
      class extends URL {
        static override createObjectURL(blob: Blob): string {
          void blob;
          created.push("blob:bundle");
          return "blob:bundle";
        }
        static override revokeObjectURL(): void {}
      },
    );
    const user = userEvent.setup();
    render(<ExportBundleButton projectId="project-1" graphId="graph-1" disabled={false} />);

    await user.click(screen.getByRole("button", { name: "Export bundle" }));

    expect(await screen.findByRole("button", { name: "Export bundle" })).toBeEnabled();
    expect(created).toEqual(["blob:bundle"]);
  });

  it("reports export failures", async () => {
    server.use(
      http.get("/api/v1/projects/:projectId/graphs/:graphId/export", () =>
        HttpResponse.json(
          { error: { code: "RESOURCE_NOT_FOUND", message: "Graph not found." } },
          { status: 404 },
        ),
      ),
    );
    const user = userEvent.setup();
    render(<ExportBundleButton projectId="nope" graphId="nope" disabled={false} />);

    await user.click(screen.getByRole("button", { name: "Export bundle" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Graph not found.");
  });

  it("stays disabled while the workspace mutates", () => {
    render(<ExportBundleButton projectId="project-1" graphId="graph-1" disabled />);

    expect(screen.getByRole("button", { name: "Export bundle" })).toBeDisabled();
  });
});
