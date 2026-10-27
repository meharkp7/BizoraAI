import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { RunsPage } from "./RunsPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
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
