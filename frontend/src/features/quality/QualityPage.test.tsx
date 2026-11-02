import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../../test/server.ts";
import { QualityPage } from "./QualityPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("QualityPage", () => {
  it("renders copilot and diagram eval scores with freshness", async () => {
    render(<QualityPage />, { wrapper });

    expect(await screen.findByText("30 of 30")).toBeInTheDocument();
    const copilot = screen.getByRole("region", { name: "Copilot eval" });
    expect(within(copilot).getAllByText("100%")).toHaveLength(2);
    expect(screen.getByText("sram-puf-tilting")).toBeInTheDocument();
    expect(screen.getByText("No gold set")).toBeInTheDocument();
    expect(screen.getByText(/Generated /)).toBeInTheDocument();
  });

  it("says plainly when evals have not run", async () => {
    server.use(
      http.get("/api/v1/quality/summary", () =>
        HttpResponse.json({
          generated_at: "2026-11-02T10:00:00+00:00",
          diagram_evals: [],
          copilot_eval: null,
        }),
      ),
    );
    render(<QualityPage />, { wrapper });

    expect(await screen.findByText("Copilot eval has not run yet.")).toBeInTheDocument();
    expect(screen.getByText("No diagram evals yet.")).toBeInTheDocument();
  });
});
