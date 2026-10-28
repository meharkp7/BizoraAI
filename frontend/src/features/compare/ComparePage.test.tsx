import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ComparePage } from "./ComparePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("ComparePage", () => {
  it("shows measured values beside the paper-reported column", async () => {
    render(<ComparePage />, { wrapper });

    fireEvent.change(screen.getByLabelText("Baseline run ID"), {
      target: { value: "run-ok" },
    });
    fireEvent.change(screen.getByLabelText("Variant run ID"), {
      target: { value: "run-bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByText("Measured vs paper-reported")).toBeInTheDocument();
    expect(
      screen.getByText("No paper-reported numbers linked yet."),
    ).toBeInTheDocument();
  });
});
