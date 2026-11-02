import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { graphFixture } from "../../test/fixtures.ts";
import { CopilotBot } from "./CopilotBot.tsx";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderBot() {
  return render(
    <CopilotBot
      projectId="project-1"
      graph={graphFixture}
      disabled={false}
      view="schematic"
      selection={null}
      onSubmit={() => {}}
    />,
    { wrapper },
  );
}

describe("CopilotBot", () => {
  it("opens the chat overlay on click and closes it", () => {
    renderBot();
    expect(screen.queryByRole("dialog", { name: "Bizora agent chat" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open Bizora agent" }));
    const dialog = screen.getByRole("dialog", { name: "Bizora agent chat" });
    // The existing panel renders inside, unchanged.
    expect(dialog).toHaveTextContent("Bizora agent");
    expect(
      dialog.querySelector('input[aria-label="Agent message"]'),
    ).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close agent chat" }));
    expect(screen.queryByRole("dialog", { name: "Bizora agent chat" })).toBeNull();
  });

  it("closes the overlay on Escape", () => {
    renderBot();
    fireEvent.click(screen.getByRole("button", { name: "Open Bizora agent" }));
    expect(screen.getByRole("dialog", { name: "Bizora agent chat" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Bizora agent chat" })).toBeNull();
  });

  it("drags to a new spot without opening the chat", () => {
    renderBot();
    const bot = screen.getByRole("button", { name: "Open Bizora agent" });
    fireEvent.pointerDown(bot, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(bot, { clientX: 300, clientY: 300, pointerId: 1 });
    fireEvent.pointerUp(bot, { clientX: 300, clientY: 300, pointerId: 1 });
    fireEvent.click(bot);
    expect(screen.queryByRole("dialog", { name: "Bizora agent chat" })).toBeNull();
    // Moved: explicit left/top now pin the bot.
    expect(bot.style.left).not.toBe("");
    expect(bot.style.top).not.toBe("");
    expect(window.localStorage.getItem("bizora.copilotBot")).not.toBeNull();
  });

  it("restores the dragged spot on reload", () => {
    window.localStorage.setItem("bizora.copilotBot", JSON.stringify({ x: 111, y: 222 }));
    try {
      renderBot();
      const bot = screen.getByRole("button", { name: "Open Bizora agent" });
      expect(bot.style.left).toBe("111px");
      expect(bot.style.top).toBe("222px");
    } finally {
      window.localStorage.removeItem("bizora.copilotBot");
    }
  });

  it("ignores a corrupt stored spot", () => {
    window.localStorage.setItem("bizora.copilotBot", "nope{");
    try {
      renderBot();
      const bot = screen.getByRole("button", { name: "Open Bizora agent" });
      expect(bot.style.left).toBe("");
    } finally {
      window.localStorage.removeItem("bizora.copilotBot");
    }
  });
});
