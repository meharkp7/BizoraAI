import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken } from "../../lib/authToken.ts";
import { useSession } from "../../lib/store.ts";
import { HomePage } from "./HomePage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/" element={children} />
          <Route path="/papers" element={<p>Papers</p>} />
          <Route path="/login" element={<p>Login</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("HomePage", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("shows logged-out visitors one product line and a login link", () => {
    render(<HomePage />, { wrapper });

    expect(
      screen.getByText("Turn scientific papers into explorable methodology graphs."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("redirects logged-in visitors to their papers", async () => {
    useSession.setState({ token: "test-token" });
    render(<HomePage />, { wrapper });

    expect(await screen.findByText("Papers")).toBeInTheDocument();
  });
});
