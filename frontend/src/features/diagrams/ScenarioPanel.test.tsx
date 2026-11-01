import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { useWhatIfScenario } from "../../lib/store.ts";
import { ScenarioPanel } from "./ScenarioPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  useWhatIfScenario.setState({ staged: [] });
});

describe("ScenarioPanel", () => {
  it("renders nothing without staged steps", () => {
    const { container } = render(<ScenarioPanel paperId="paper-1" />, { wrapper });
    expect(container).toBeEmptyDOMElement();
  });

  it("runs staged steps together and reports side by side", async () => {
    useWhatIfScenario.setState({
      staged: [
        { paperId: "paper-1", nodeId: "a", nodeLabel: "Step A", params: { x: "1" } },
        { paperId: "paper-1", nodeId: "b", nodeLabel: "Step B", params: { y: "2" } },
        { paperId: "other", nodeId: "c", nodeLabel: "Step C", params: { z: "3" } },
      ],
    });
    render(<ScenarioPanel paperId="paper-1" />, { wrapper });
    expect(screen.getByText("Scenario (2 steps)")).toBeInTheDocument();
    expect(screen.queryByText("Step C")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Run all" }));
    // The mock answers every node with the same estimate.
    expect(await screen.findAllByText(/Estimated 10000 bits/)).toHaveLength(2);
    expect(screen.getByText(/estimated independently/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(useWhatIfScenario.getState().staged).toHaveLength(1);
    expect(useWhatIfScenario.getState().staged[0]?.nodeId).toBe("c");
  });
});
