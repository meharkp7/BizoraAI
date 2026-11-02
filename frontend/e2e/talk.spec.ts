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

const diagrams = {
  methodology: {
    version: 1,
    title: "E2E methodology",
    groups: [],
    nodes: [
      {
        id: "m-input",
        label: "Patch input",
        kind: "input",
        group: null,
        detail: null,
        params: {},
        confidence: 0.9,
        evidence: { page: 2, figure_id: null, quote: "Images are split into patches." },
      },
      {
        id: "m-encode",
        label: "Transformer encoder",
        kind: "model",
        group: null,
        detail: "Twelve stacked blocks.",
        params: { layers: 12 },
        confidence: 0.95,
        evidence: { page: 4, figure_id: null, quote: "The encoder stacks twelve blocks." },
      },
    ],
    edges: [{ from: "m-input", to: "m-encode", label: null, kind: "data" }],
  },
  circuits: [],
  structure: null,
  validation: {},
  sources: {},
};

const answer = {
  reply: "Found m-encode (Transformer encoder) on the methodology tab.",
  cards: [
    {
      kind: "diagram",
      title: "Diagram element m-encode",
      body: "m-encode — Transformer encoder (methodology tab)",
      component_ids: [],
      node_id: null,
      diagram_ref: {
        view: "methodology",
        element_id: "m-encode",
        label: "Transformer encoder",
      },
    },
  ],
  proposal: null,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/papers/*/diagrams", async (route) => {
    await route.fulfill({ json: diagrams });
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
    await route.fulfill({
      contentType: "text/event-stream",
      body:
        `event: status\ndata: {"message":"Answering from the workspace graph…"}\n\n` +
        `event: done\ndata: ${JSON.stringify({ response: answer })}\n\n`,
    });
  });
});

test("copilot locates a diagram element and jumps the viewer to it", async ({ page }) => {
  await page.goto("/g/project-1/graph-1");
  await expect(page.getByRole("heading", { name: "Vision transformer" })).toBeVisible();

  await page.getByRole("button", { name: "Open Bizora agent" }).click();
  const chat = page.getByRole("dialog", { name: "Bizora agent chat" });
  await chat.getByLabel("Agent message").fill("show m-encode");
  await chat.getByRole("button", { name: "Ask" }).click();

  await expect(chat.getByText("Diagram element m-encode")).toBeVisible();
  await chat.getByRole("button", { name: "Show in diagram" }).click();

  const inspector = page.getByRole("region", { name: "Inspector" });
  await expect(inspector).toContainText("Transformer encoder");
  await expect(inspector).toContainText("Twelve stacked blocks.");
});
