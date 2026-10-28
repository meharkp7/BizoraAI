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
});
