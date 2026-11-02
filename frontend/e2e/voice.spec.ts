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
  // transcript as soon as listening starts, and the fake synthesizer
  // records everything the agent reads aloud.
  await page.addInitScript(() => {
    class FakeRecognition {
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onspeechstart: (() => void) | null = null;
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
    class FakeUtterance {
      text: string;
      voice: unknown = null;
      rate = 1;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(text: string) {
        this.text = text;
      }
    }
    const scope = globalThis as unknown as Record<string, unknown>;
    scope.SpeechRecognition = FakeRecognition;
    scope.SpeechSynthesisUtterance = FakeUtterance;
    scope.__spoken = [];
    // window.speechSynthesis is a read-only accessor in Chrome: a plain
    // assignment silently fails, so shadow it with a defined property.
    Object.defineProperty(globalThis, "speechSynthesis", {
      value: {
        speak: (utterance: FakeUtterance) => {
          (scope.__spoken as string[]).push(utterance.text);
          queueMicrotask(() => utterance.onend?.());
        },
        cancel: () => {},
        getVoices: () => [{ name: "Test Voice", lang: "en-IN" }],
      },
      configurable: true,
    });
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

test("voice chat asks hands-free and reads the answer aloud", async ({ page }) => {
  let voiceFlag: unknown = null;
  // Registered after the shared routes, so this handler wins.
  await page.route("**/revisions/*/copilot/stream", async (route) => {
    voiceFlag = route.request().postDataJSON()?.voice ?? null;
    const response = {
      reply: "The 2N3904 is a general purpose NPN transistor.",
      cards: [],
      proposal: null,
    };
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ response })}\n\n`,
    });
  });

  await page.goto("/g/project-1/graph-1");
  await page.getByRole("button", { name: "Open research copilot" }).click();

  const chat = page.getByRole("dialog", { name: "Research copilot chat" });
  await chat.getByRole("button", { name: "Voice chat" }).click();

  // The fake recognizer emits its transcript on start: no typing needed.
  await expect(chat.getByText("find NPN transistor")).toBeVisible();
  await expect(
    chat.getByText("The 2N3904 is a general purpose NPN transistor."),
  ).toBeVisible();
  await expect(chat.getByText("Listening — just talk.")).toBeVisible();
  expect(voiceFlag).toBe(true);

  await expect
    .poll(async () =>
      page.evaluate(
        () => (globalThis as unknown as { __spoken: string[] }).__spoken,
      ),
    )
    .toEqual(["The 2N3904 is a general purpose NPN transistor."]);

  await chat.getByRole("button", { name: "End voice chat" }).click();
  await expect(chat.getByText("Listening — just talk.")).toBeHidden();
});
