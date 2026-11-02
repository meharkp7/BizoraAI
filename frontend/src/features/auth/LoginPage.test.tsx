import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { clearAuthToken, getAuthToken } from "../../lib/authToken.ts";
import { useSession } from "../../lib/store.ts";
import { LoginPage } from "./LoginPage.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={["/login"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/login" element={children} />
          <Route path="/papers" element={<p>Papers</p>} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    clearAuthToken();
    useSession.setState({ token: null });
  });

  it("logs in, stores the token, and lands on papers", async () => {
    const user = userEvent.setup();
    render(<LoginPage />, { wrapper });

    await user.type(screen.getByLabelText("Email"), "me@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-9");
    const form = screen.getByRole("form", { name: "Login form" });
    await user.click(within(form).getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Papers")).toBeInTheDocument();
    expect(getAuthToken()).toBe("test-token");
  });

  it("registers a new account and stores the token", async () => {
    const user = userEvent.setup();
    render(<LoginPage />, { wrapper });

    const modes = screen.getByRole("group", { name: "Login or register" });
    await user.click(within(modes).getByRole("button", { name: "Create account" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Name"), "New");
    await user.type(screen.getByLabelText(/Password/), "correct-horse-9");
    const form = screen.getByRole("form", { name: "Login form" });
    await user.click(within(form).getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Papers")).toBeInTheDocument();
    expect(getAuthToken()).toBe("test-token");
  });

  it("shows the server message on bad credentials", async () => {
    const user = userEvent.setup();
    render(<LoginPage />, { wrapper });

    await user.type(screen.getByLabelText("Email"), "ghost@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-horse-9");
    const form = screen.getByRole("form", { name: "Login form" });
    await user.click(within(form).getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(getAuthToken()).toBeNull();
  });
});
