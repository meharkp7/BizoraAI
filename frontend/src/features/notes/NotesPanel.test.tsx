import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken, setAuthToken } from "../../lib/authToken.ts";
import { useSession } from "../../lib/store.ts";
import { resetNotesStore } from "../../test/server.ts";
import { NotesPanel } from "./NotesPanel.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("NotesPanel", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
    resetNotesStore();
  });

  function login(): void {
    setAuthToken("test-token");
    useSession.setState({ token: "test-token" });
  }

  it("renders nothing without a paper", () => {
    const { container } = render(<NotesPanel paperId={null} />, { wrapper });
    expect(container).toBeEmptyDOMElement();
  });

  it("asks logged-out visitors to log in", () => {
    render(<NotesPanel paperId="paper-papers" />, { wrapper });
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
  });

  it("lists, adds, edits, and deletes notes", async () => {
    login();
    const user = userEvent.setup();
    render(<NotesPanel paperId="paper-papers" />, { wrapper });

    expect(await screen.findByText("Reproduce the tilt test first.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("New note"), "Check the BER table.");
    await user.click(screen.getByRole("button", { name: "Add note" }));
    expect(await screen.findByText("Check the BER table.")).toBeInTheDocument();

    const added = screen.getByText("Check the BER table.").closest("li") as HTMLElement;
    await user.click(within(added).getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Note text"));
    await user.type(screen.getByLabelText("Note text"), "Check the BER table twice.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Check the BER table twice.")).toBeInTheDocument();

    const edited = screen.getByText("Check the BER table twice.").closest("li") as HTMLElement;
    await user.click(within(edited).getByRole("button", { name: /Delete note/ }));
    await screen.findByText("Reproduce the tilt test first.");
    expect(screen.queryByText("Check the BER table twice.")).toBeNull();
  });
});
