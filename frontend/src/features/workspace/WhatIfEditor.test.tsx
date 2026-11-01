import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useWhatIfScenario } from "../../lib/store.ts";
import { WhatIfEditor } from "./WhatIfEditor.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderEditor(params: { label: string; value: string }[]) {
  return render(
    <dl>
      <WhatIfEditor
        paperId="paper-1"
        nodeId="fabricate"
        nodeLabel="Fabricate array"
        params={params}
      />
    </dl>,
    { wrapper },
  );
}

describe("WhatIfEditor", () => {
  it("edits stated settings and shows the grounded estimate", async () => {
    renderEditor([{ label: "cell_count", value: "2000" }]);

    const run = screen.getByRole("button", { name: "Run what-if" });
    expect(run).toBeDisabled();
    fireEvent.change(screen.getByLabelText("cell_count"), {
      target: { value: "5000" },
    });
    expect(run).toBeEnabled();
    fireEvent.click(run);

    expect(await screen.findByText(/Estimated 10000 bits/)).toBeInTheDocument();
    expect(screen.getByText(/not a measured result/)).toBeInTheDocument();
    expect(screen.getAllByText(/two bits per cell/)).toHaveLength(2);
    expect(screen.getByText(/p\. 3/)).toBeInTheDocument();
    expect(screen.getByText(/Yield holds/)).toBeInTheDocument();
    expect(screen.getByText(/Confidence 0\.62/)).toBeInTheDocument();
  });

  it("resets values and clears the outcome", async () => {
    renderEditor([{ label: "cell_count", value: "2000" }]);
    fireEvent.change(screen.getByLabelText("cell_count"), {
      target: { value: "5000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run what-if" }));
    expect(await screen.findByText(/Estimated 10000 bits/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByLabelText("cell_count")).toHaveValue("2000");
    expect(screen.queryByText(/Estimated 10000 bits/)).toBeNull();
    expect(screen.getByRole("button", { name: "Run what-if" })).toBeDisabled();
  });

  it("says plainly when the paper states no settings", () => {
    renderEditor([]);
    expect(screen.getByText(/no settings for this step/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run what-if" })).toBeNull();
  });

  it("refuses to run blank settings", () => {
    renderEditor([{ label: "cell_count", value: "2000" }]);
    fireEvent.change(screen.getByLabelText("cell_count"), { target: { value: "  " } });
    expect(screen.getByRole("button", { name: "Run what-if" })).toBeDisabled();
    expect(screen.getByText(/must be non-empty/)).toBeInTheDocument();
  });

  it("accumulates past runs for comparison", async () => {
    renderEditor([{ label: "cell_count", value: "2000" }]);
    fireEvent.change(screen.getByLabelText("cell_count"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Run what-if" }));
    expect(await screen.findByText(/Estimated 10000 bits/)).toBeInTheDocument();
    expect(screen.queryByText(/Past runs this session/)).toBeNull();

    fireEvent.change(screen.getByLabelText("cell_count"), { target: { value: "6000" } });
    fireEvent.click(screen.getByRole("button", { name: "Run what-if" }));
    expect(await screen.findByText(/Past runs this session \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/cell_count: 2000 → 5000/)).toBeInTheDocument();
    expect(screen.getByText(/cell_count: 2000 → 6000/)).toBeInTheDocument();
  });

  it("stages the current values for a multi-node scenario", () => {
    renderEditor([{ label: "cell_count", value: "2000" }]);
    const stage = screen.getByRole("button", { name: "Stage" });
    expect(stage).toBeDisabled();
    fireEvent.change(screen.getByLabelText("cell_count"), { target: { value: "5000" } });
    expect(stage).toBeEnabled();
    fireEvent.click(stage);
    expect(screen.getByRole("button", { name: /Staged/ })).toBeInTheDocument();
    const staged = useWhatIfScenario.getState().staged;
    expect(staged).toHaveLength(1);
    expect(staged[0]).toMatchObject({
      paperId: "paper-1",
      nodeId: "fabricate",
      nodeLabel: "Fabricate array",
      params: { cell_count: "5000" },
    });
    useWhatIfScenario.getState().clearScenario("paper-1");
  });
});
