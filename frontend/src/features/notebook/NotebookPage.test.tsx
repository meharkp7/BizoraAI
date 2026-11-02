import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken, setAuthToken } from "../../lib/authToken.ts";
import { server } from "../../test/server.ts";
import { NotebookPage, buildMarkdown } from "./NotebookPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("NotebookPage", () => {
  beforeEach(() => {
    clearAuthToken();
  });

  it("assembles revisions, runs with metrics, and the export", async () => {
    render(<NotebookPage projectId="project-1" graphId="graph-1" />, { wrapper });

    const history = await screen.findByRole("region", { name: "Revision history" });
    expect(within(history).getByText("v2")).toBeInTheDocument();
    expect(within(history).getByText("v1")).toBeInTheDocument();

    const runs = screen.getByRole("region", { name: "Experiment runs" });
    expect(within(runs).getByText("run-ok")).toBeInTheDocument();
    expect(await within(runs).findByText("accuracy = 0.92")).toBeInTheDocument();
    expect(within(runs).getByText("run-bad")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Export Markdown" })).toBeEnabled();
  });

  it("shows paper notes when logged in", async () => {
    setAuthToken("test-token");
    server.use(
      http.get("/api/v1/papers/:paperId/notes", () =>
        HttpResponse.json([
          {
            id: 7,
            paper_id: "paper-1",
            body: "Check the tilt table.",
            created_at: "2026-01-04T00:00:00+00:00",
            updated_at: "2026-01-04T00:00:00+00:00",
          },
        ]),
      ),
    );
    render(<NotebookPage projectId="project-1" graphId="graph-1" />, { wrapper });

    const notes = await screen.findByRole("region", { name: "Paper notes" });
    expect(await within(notes).findByText("Check the tilt table.")).toBeInTheDocument();
  });

  it("explains missing notes when logged out", async () => {
    render(<NotebookPage projectId="project-1" graphId="graph-1" />, { wrapper });

    const notes = await screen.findByRole("region", { name: "Paper notes" });
    expect(await within(notes).findByText("No notes linked.")).toBeInTheDocument();
  });
});

describe("buildMarkdown", () => {
  it("renders revisions, runs, and notes as markdown", () => {
    const markdown = buildMarkdown({
      projectId: "project-1",
      graphId: "graph-1",
      title: "Vision transformer",
      revisions: [
        {
          version: 1,
          title: "Vision transformer",
          created_by: "test",
          created_at: "2026-01-01",
        },
      ],
      runs: [
        {
          run_id: "run-ok",
          config: { adapter_id: "bizora.deterministic-test" } as never,
          state: "succeeded",
          created_at: "",
          started_at: null,
          finished_at: null,
          error: null,
        },
      ],
      notes: [
        {
          id: 1,
          paper_id: "paper-1",
          body: "Check the tilt table.",
          created_at: "",
          updated_at: "2026-01-04",
        },
      ],
    });

    expect(markdown).toContain("# Notebook: Vision transformer");
    expect(markdown).toContain("- v1 Vision transformer (test, 2026-01-01)");
    expect(markdown).toContain("- run-ok: bizora.deterministic-test, succeeded");
    expect(markdown).toContain("- Check the tilt table. (2026-01-04)");
  });
});
