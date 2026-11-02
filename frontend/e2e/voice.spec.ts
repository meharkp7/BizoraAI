import { expect, test } from "@playwright/test";

const graph = {
  schema_version: "1.0",
  project_id: "project-1",
  graph_id: "graph-1",
  version: 2,
  title: "Vision transformer",
  source_ids: ["paper-1"],
  nodes: [
    {
      id: "encoder",
      kind: "model",
      label: "Transformer encoder",
      description: null,
      config: { layers: 12 },
      input_shape: [null, 768],
      output_shape: [null, 768],
      evidence: [],
      provenance: "extracted",
      confidence: null,
    },
  ],
  edges: [],
  created_by: "test",
  parent_version: 1,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/graph-1/copilot/threads", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          thread_id: "thread-1",
          title: "New conversation",
          turn_count: 0,
          updated_at: "2026-11-02T00:00:00+00:00",
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.route("**/graph-1/copilot/threads/*", async (route) => {
    await route.fulfill({
      json: { thread_id: "thread-1", title: "New conversation", turns: [] },
    });
  });
  await page.route("**/revisions/*/copilot/stream", async (route) => {
    const response = {
      reply: "Closest library matches: 2N3904 NPN transistor.",
      cards: [],
      proposal: null,
    };
    await route.fulfill({
      contentType: "text/event-stream",
      body:
        `event: status\ndata: {"message":"Answering from the workspace graph…"}\n\n` +
        `event: done\ndata: ${JSON.stringify({ response })}\n\n`,
    });
  });
  // Deterministic speech input: the fake recognizer emits one final
  // transcript as soon as dictation starts.
  await page.addInitScript(() => {
    class FakeRecognition {
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start(): void {
        queueMicrotask(() => {
          this.onresult?.({
            resultIndex: 0,
            results: [{ isFinal: true, 0: { transcript: "find NPN transistor" } }],
          });
        });
      }
      stop(): void {
        this.onend?.();
      }
      abort(): void {}
    }
    (globalThis as unknown as Record<string, unknown>).SpeechRecognition =
      FakeRecognition;
  });
});

test("dictation fills an editable message that asks normally", async ({ page }) => {
  await page.goto("/g/project-1/graph-1");
  await page.getByRole("button", { name: "Open research copilot" }).click();

  const chat = page.getByRole("dialog", { name: "Research copilot chat" });
  await chat.getByRole("button", { name: "Dictate message" }).click();

  const input = chat.getByLabel("Copilot message");
  await expect(input).toHaveValue("find NPN transistor");

  await input.fill("find NPN transistor edited");
  await chat.getByRole("button", { name: "Ask" }).click();
  await expect(chat.getByText(/Closest library matches/)).toBeVisible();
});
