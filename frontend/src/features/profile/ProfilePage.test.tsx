import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken, setAuthToken } from "../../lib/authToken.ts";
import { useSession } from "../../lib/store.ts";
import { ProfilePage } from "./ProfilePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/profile"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/profile" element={children} />
          <Route path="/" element={<p>Homepage</p>} />
          <Route path="/login" element={<p>Login</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ProfilePage", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("asks logged-out visitors to log in", () => {
    render(<ProfilePage />, { wrapper });
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
  });

  it("shows the account, the library, and logs out", async () => {
    setAuthToken("test-token");
    useSession.setState({ token: "test-token" });
    const user = userEvent.setup();
    render(<ProfilePage />, { wrapper });

    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AlphaFold paper" })).toHaveAttribute(
      "href",
      "/g/project-papers/graph-papers",
    );

    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByText("Homepage")).toBeInTheDocument();
    expect(useSession.getState().token).toBeNull();
  });

  it("shows estimated spend and the enforced caps", async () => {
    setAuthToken("test-token");
    useSession.setState({ token: "test-token" });
    render(<ProfilePage />, { wrapper });

    const section = await screen.findByRole("region", { name: "Usage and spend" });
    expect(await screen.findAllByText("$0.01 · 1 unmetered")).toHaveLength(2);
    expect(section).toHaveTextContent("$0.01");
    expect(section).toHaveTextContent("1 unmetered");
    expect(section).toHaveTextContent("$25.00");
    expect(section).toHaveTextContent("$5.00");
    expect(section).toHaveTextContent("50");
    expect(section).toHaveTextContent("estimates");
  });
});
