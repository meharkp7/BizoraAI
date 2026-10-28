import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { SimulationPreview } from "./SimulationPreview.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("SimulationPreview", () => {
  it("renders pack sections and warnings", async () => {
    render(<SimulationPreview projectId="project-1" graphId="graph-1" version={1} />, {
      wrapper,
    });

    expect(await screen.findByRole("heading", { name: "SPICE circuit preview" })).toBeInTheDocument();
    expect(screen.getByText("Pack: electronics")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Netlist" })).toBeInTheDocument();
    expect(screen.getByText(/R1 in out 1k/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Simulation warnings" })).toBeInTheDocument();
    expect(screen.getByText(/missing_pullup/)).toBeInTheDocument();
  });

  it("stays hidden when the revision has no preview", async () => {
    server.use(
      http.get(
        "/api/v1/graphs/:projectId/:graphId/revisions/:version/simulation-preview",
        () => HttpResponse.json(null),
      ),
    );
    const { container } = render(
      <SimulationPreview projectId="project-1" graphId="graph-1" version={1} />,
      { wrapper },
    );

    await waitFor(() => {
      expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
    });
    expect(container).toBeEmptyDOMElement();
  });
});
