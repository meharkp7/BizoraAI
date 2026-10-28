import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useLibrarySelection } from "../../lib/store.ts";
import { LibraryPanel } from "./LibraryPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("LibraryPanel", () => {
  it("searches the library and distinguishes exact parts from generics", async () => {
    useLibrarySelection.setState({ selectedComponentId: null, indexTab: "library" });
    render(<LibraryPanel />, { wrapper });

    expect(await screen.findByText("2N3904 NPN transistor")).toBeInTheDocument();
    expect(screen.getByText("Resistor (generic)")).toBeInTheDocument();
    expect(screen.getByText("exact part")).toBeInTheDocument();
    expect(screen.getByText("generic")).toBeInTheDocument();
  });

  it("filters results by search text and opens the detail view", async () => {
    useLibrarySelection.setState({ selectedComponentId: null, indexTab: "library" });
    const user = userEvent.setup();
    render(<LibraryPanel />, { wrapper });

    await user.type(screen.getByLabelText("Search components"), "resistor");

    expect(await screen.findByText("Resistor (generic)")).toBeInTheDocument();
    expect(screen.queryByText("2N3904 NPN transistor")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Resistor \(generic\)/ }));
    expect(useLibrarySelection.getState().selectedComponentId).toBe("resistor-generic");
  });

  it("filters exact parts only", async () => {
    useLibrarySelection.setState({ selectedComponentId: null, indexTab: "library" });
    const user = userEvent.setup();
    render(<LibraryPanel />, { wrapper });

    await screen.findByText("2N3904 NPN transistor");
    await user.selectOptions(screen.getByLabelText("Identity"), "exact");

    expect(screen.getByText("2N3904 NPN transistor")).toBeInTheDocument();
    expect(screen.queryByText("Resistor (generic)")).not.toBeInTheDocument();
  });
});
