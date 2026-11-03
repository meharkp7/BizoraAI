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

/** Raw multipart bodies the app uploaded for transcription. */
const transcribeUploads: string[] = [];

/** Feed one 4096-sample frame into the latest scripted capture. */
async function feedFrame(page: { evaluate: (fn: (loud: boolean) => void, loud: boolean) => Promise<void> }, loud: boolean): Promise<void> {
  await page.evaluate((isLoud: boolean) => {
    const scope = globalThis as unknown as {
      __processors?: Array<{ onaudioprocess: ((event: unknown) => void) | null }>;
    };
    const processor = (scope.__processors ?? []).at(-1);
    const frame = new Float32Array(4096).fill(isLoud ? 0.2 : 0.0);
    processor?.onaudioprocess?.({ inputBuffer: { getChannelData: () => frame } });
  }, loud);
}

/** Speak briefly, then hold silence until the utterance endpoint fires. */
async function speakUtterance(
  page: { evaluate: (fn: (loud: boolean) => void, loud: boolean) => Promise<void> },
  silenceFrames: number,
): Promise<void> {
  await feedFrame(page, true);
  await feedFrame(page, true);
  for (let i = 0; i < silenceFrames; i += 1) {
    await feedFrame(page, false);
  }
}

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
  transcribeUploads.length = 0;
  await page.route("**/graph-1/copilot/transcribe", async (route) => {
    transcribeUploads.push(route.request().postDataBuffer()?.toString("latin1") ?? "");
    await route.fulfill({
      json: {
        transcript: "find NPN transistor",
        audio_duration_ms: 900,
        session_id: "s-1",
      },
    });
  });
  // Deterministic speech input: a scripted AudioContext lets the test
  // feed loud frames (speech) then quiet frames (silence) into the real
  // capture/VAD/WAV path, and the fake synthesizer records everything
  // the agent reads aloud.
  await page.addInitScript(() => {
    interface FakeProcessor {
      onaudioprocess: ((event: unknown) => void) | null;
      connect: () => void;
      disconnect: () => void;
    }
    class FakeAudioContext {
      readonly sampleRate = 16000;
      readonly destination = {};
      createMediaStreamSource(): { connect: () => void; disconnect: () => void } {
        return { connect: () => {}, disconnect: () => {} };
      }
      createGain(): { gain: { value: number }; connect: () => void; disconnect: () => void } {
        return { gain: { value: 0 }, connect: () => {}, disconnect: () => {} };
      }
      createScriptProcessor(): FakeProcessor {
        const processor: FakeProcessor = {
          onaudioprocess: null,
          connect: () => {},
          disconnect: () => {},
        };
        const scope = globalThis as unknown as { __processors?: FakeProcessor[] };
        scope.__processors = [...(scope.__processors ?? []), processor];
        return processor;
      }
      close(): Promise<void> {
        return Promise.resolve();
      }
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
    scope.AudioContext = FakeAudioContext;
    scope.MediaStream = class {};
    scope.__spoken = [];
    scope.__processors = [];
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: () => Promise.resolve({ getTracks: () => [] }) },
    });
    scope.SpeechSynthesisUtterance = FakeUtterance;
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
  await page.getByRole("button", { name: "Open Bizora agent" }).click();

  const chat = page.getByRole("dialog", { name: "Bizora agent chat" });
  await chat.getByRole("button", { name: "Dictate message" }).click();
  await page.waitForFunction(
    () =>
      ((globalThis as unknown as { __processors?: unknown[] }).__processors ?? []).length > 0,
  );

  // Dictation endpoints on 2.5s of silence: ten 256ms frames.
  await speakUtterance(page, 10);

  const input = chat.getByLabel("Agent message");
  await expect(input).toHaveValue("find NPN transistor");
  expect(transcribeUploads).toHaveLength(1);
  expect(transcribeUploads[0]).toContain("RIFF");
  expect(transcribeUploads[0]).toContain("WAVE");

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
  await page.getByRole("button", { name: "Open Bizora agent" }).click();

  const chat = page.getByRole("dialog", { name: "Bizora agent chat" });
  await chat.getByRole("button", { name: "Voice chat" }).click();
  await page.waitForFunction(
    () =>
      ((globalThis as unknown as { __processors?: unknown[] }).__processors ?? []).length > 0,
  );

  // The scripted mic speaks one utterance: no typing needed.
  await speakUtterance(page, 5);
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
