import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { ReportedPanel } from "./ReportedPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ReportedPanel", () => {
  it("labels the paper's numbers as reported by the paper", async () => {
    render(<ReportedPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    const panel = await screen.findByRole("region", { name: "Reported results" });
    await screen.findByText("reported by paper");
    expect(panel).toHaveTextContent("accuracy");
    expect(panel).toHaveTextContent("0.89");
    expect(panel).toHaveTextContent("reported by paper");
    expect(panel).toHaveTextContent("Ours: 0.89 (Accuracy)");
  });

  it("filters metrics by name", async () => {
    render(<ReportedPanel projectId="project-1" graphId="graph-1" />, { wrapper });

    await screen.findByRole("region", { name: "Reported results" });
    await screen.findByRole("textbox", { name: "Filter reported metrics" });
    await userEvent.type(
      screen.getByRole("textbox", { name: "Filter reported metrics" }),
      "latency",
    );
    expect(screen.getByText("No reported metrics match this filter.")).toBeInTheDocument();
  });

  it("says plainly when tables hold no numbers", async () => {
    server.use(
      http.get("/api/v1/graphs/:projectId/:graphId/reported-metrics", () =>
        HttpResponse.json([]),
      ),
    );
    render(<ReportedPanel projectId="project-9" graphId="graph-9" />, { wrapper });

    expect(
      await screen.findByText(/No reported numbers in this graph's tables/),
    ).toBeInTheDocument();
  });
});
