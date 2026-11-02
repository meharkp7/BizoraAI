import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { RunDetailPage, RunsPage } from "./RunsPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

/** Clearly-marked fake: a silent EventSource that only records its URL. */
class SilentEventSource {
  url: string;

  constructor(url: string) {
    this.url = url;
  }

  addEventListener(): void {}

  removeEventListener(): void {}

  close(): void {}
}

describe("RunsPage", () => {
  it("lists runs newest with state badges", async () => {
    render(<RunsPage projectId="project-1" graphId="graph-1" />, { wrapper });
    expect(await screen.findByText("run-ok")).toBeInTheDocument();
    expect(screen.getByText("run-bad")).toBeInTheDocument();
    expect(screen.getByLabelText("state: succeeded")).toBeInTheDocument();
    expect(screen.getByText("adapter_failed: boom")).toBeInTheDocument();
  });

  it("explains an empty run list", async () => {
    server.use(http.get("/api/v1/experiments/runs", () => HttpResponse.json([])));
    render(<RunsPage projectId="project-1" graphId="graph-1" />, { wrapper });
    expect(await screen.findByText("No runs yet.")).toBeInTheDocument();
  });

  it("shows each run's estimated or unmetered cost", async () => {
    server.use(
      http.get("/api/v1/usage/runs", () =>
        HttpResponse.json([
          {
            run_id: "run-ok",
            project_id: "project-1",
            graph_id: "graph-1",
            calls: 2,
            input_tokens: 5000,
            output_tokens: 1000,
            cost_usd_estimated: 0.03,
            unmetered: false,
            last_used_at: "2026-11-01T09:00:00+00:00",
          },
          {
            run_id: "run-bad",
            project_id: "project-1",
            graph_id: "graph-1",
            calls: 1,
            input_tokens: 0,
            output_tokens: 0,
            cost_usd_estimated: null,
            unmetered: true,
            last_used_at: "2026-11-02T09:00:00+00:00",
          },
        ]),
      ),
    );
    render(<RunsPage projectId="project-1" graphId="graph-1" />, { wrapper });

    expect(await screen.findByText("run-ok")).toBeInTheDocument();
    expect(screen.getByText("$0.03 estimated")).toBeInTheDocument();
    expect(screen.getByText("Unmetered")).toBeInTheDocument();
  });
});

describe("RunDetailPage", () => {
  it("streams live telemetry for an active run", async () => {
    const sources: SilentEventSource[] = [];
    render(
      <RunDetailPage
        runId="run-pending"
        eventSourceFactory={(url: string) => {
          const source = new SilentEventSource(url);
          sources.push(source);
          return source as unknown as EventSource;
        }}
      />,
      { wrapper },
    );

    expect(await screen.findByLabelText("Live run telemetry")).toBeInTheDocument();
    expect(sources).toHaveLength(1);
    expect(sources[0].url).toBe(
      "/api/v1/experiments/runs/run-pending/telemetry/stream?from_seq=0",
    );
  });

  it("omits the live stream for a finished run", async () => {
    render(<RunDetailPage runId="run-ok" />, { wrapper });

    expect(await screen.findByText("accuracy")).toBeInTheDocument();
    expect(screen.queryByLabelText("Live run telemetry")).not.toBeInTheDocument();
  });

  it("shows the run's estimated cost in its record", async () => {
    server.use(
      http.get("/api/v1/usage/runs", () =>
        HttpResponse.json([
          {
            run_id: "run-ok",
            project_id: "project-1",
            graph_id: "graph-1",
            calls: 2,
            input_tokens: 5000,
            output_tokens: 1000,
            cost_usd_estimated: 0.03,
            unmetered: false,
            last_used_at: "2026-11-01T09:00:00+00:00",
          },
        ]),
      ),
    );
    render(<RunDetailPage runId="run-ok" />, { wrapper });

    expect(await screen.findByText("$0.03 estimated")).toBeInTheDocument();
  });
});
