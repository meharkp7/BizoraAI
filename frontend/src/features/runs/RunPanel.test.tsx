import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { graphFixture } from "../../test/fixtures.ts";
import { RunPanel } from "./RunPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("RunPanel", () => {
  it("creates and executes a run for the current revision", async () => {
    let createdConfig: unknown = null;
    server.use(
      http.post("/api/v1/experiments/runs", async ({ request }) => {
        const body = (await request.json()) as { run_id: string; config: unknown };
        createdConfig = body.config;
        return HttpResponse.json(
          { run_id: body.run_id, state: "pending" },
          { status: 201 },
        );
      }),
      http.post("/api/v1/experiments/runs/:runId/execute", ({ params }) =>
        HttpResponse.json({ run_id: params.runId, state: "succeeded" }),
      ),
    );
    render(<RunPanel projectId="project-1" graph={graphFixture} />, { wrapper });

    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: `Run v${graphFixture.version}` }));

    expect(await screen.findByText("Run finished:")).toBeInTheDocument();
    expect(createdConfig).toMatchObject({
      graph_id: graphFixture.graph_id,
      graph_version: graphFixture.version,
      adapter_id: "bizora.deterministic-test",
      seed: 7,
    });
  });

  it("replays telemetry for the finished run", async () => {
    const urls: string[] = [];
    server.use(
      http.post("/api/v1/experiments/runs", async ({ request }) => {
        const body = (await request.json()) as { run_id: string };
        return HttpResponse.json(
          { run_id: body.run_id, state: "pending" },
          { status: 201 },
        );
      }),
      http.post("/api/v1/experiments/runs/:runId/execute", ({ params }) =>
        HttpResponse.json({ run_id: params.runId, state: "succeeded" }),
      ),
    );
    render(
      <RunPanel
        projectId="project-1"
        graph={graphFixture}
        eventSourceFactory={(url: string) => {
          urls.push(url);
          return {
            addEventListener: () => {},
            removeEventListener: () => {},
            close: () => {},
          } as unknown as EventSource;
        }}
      />,
      { wrapper },
    );
    expect(screen.queryByLabelText("Live run telemetry")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: `Run v${graphFixture.version}` }));

    expect(await screen.findByLabelText("Live run telemetry")).toBeInTheDocument();
    expect(urls).toHaveLength(1);
    expect(urls[0]).toMatch(
      /^\/api\/v1\/experiments\/runs\/.+\/telemetry\/stream\?from_seq=0$/,
    );
  });

  it("submits the selected adapter instead of the default", async () => {
    let createdConfig: unknown = null;
    server.use(
      http.get("/api/v1/experiments/adapters", () =>
        HttpResponse.json([
          {
            adapter_id: "bizora.deterministic-test",
            adapter_version: "0.1.0",
            description: "Deterministic validation.",
          },
          {
            adapter_id: "bizora.ngspice",
            adapter_version: "0.1.0",
            description: "SPICE-class circuit simulation.",
          },
        ]),
      ),
      http.post("/api/v1/experiments/runs", async ({ request }) => {
        const body = (await request.json()) as { run_id: string; config: unknown };
        createdConfig = body.config;
        return HttpResponse.json(
          { run_id: body.run_id, state: "pending" },
          { status: 201 },
        );
      }),
      http.post("/api/v1/experiments/runs/:runId/execute", ({ params }) =>
        HttpResponse.json({ run_id: params.runId, state: "succeeded" }),
      ),
    );
    render(<RunPanel projectId="project-1" graph={graphFixture} />, { wrapper });

    await screen.findByRole("option", { name: /bizora\.ngspice/ });
    fireEvent.change(screen.getByLabelText("Adapter"), {
      target: { value: "bizora.ngspice" },
    });
    fireEvent.click(screen.getByRole("button", { name: `Run v${graphFixture.version}` }));

    expect(await screen.findByText("Run finished:")).toBeInTheDocument();
    expect(createdConfig).toMatchObject({
      adapter_id: "bizora.ngspice",
      adapter_version: "0.1.0",
    });
  });
});
