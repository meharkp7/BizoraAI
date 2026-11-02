import { expect, test, type Page } from "@playwright/test";

const WORKSPACE_URL = "/g/project-1/graph-1?v=2";

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

const answer = {
  reply: "The filter corner is 4 kHz per the paper.",
  cards: [
    {
      kind: "evidence",
      title: "Paper evidence",
      body: "Source: paper-1 · Page 2",
      component_ids: [],
      node_id: "encoder",
      source: {
        source_id: "paper-1",
        page: 2,
        quote: "The filter corner is 4 kHz per the paper",
        figure_label: null,
      },
    },
  ],
  proposal: null,
};

async function mockWorkspace(page: Page) {
  await page.route("**/api/v1/graphs/**/revisions/*", async (route) => {
    const url = route.request().url();
    if (route.request().method() !== "GET" || !url.endsWith("/revisions/2")) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: graph });
  });
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({
      json: [
        {
          version: 2,
          parent_version: 1,
          title: "Vision transformer",
          created_by: "test",
          created_at: "2026-01-02T00:00:00Z",
        },
      ],
    });
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
        `event: status\ndata: {"message":"Consulting read_evidence…"}\n\n` +
        `event: done\ndata: ${JSON.stringify({ response: answer })}\n\n`,
    });
  });
  await page.route("**/api/v1/papers/paper-1/text", async (route) => {
    await route.fulfill({
      json: {
        source_id: "paper-1",
        page_count: 2,
        sha256: "0".repeat(64),
        text: "[Page 1]\nIntro words about the design.\n[Page 2]\nThe filter corner is 4 kHz per the paper, measured at room temperature.",
      },
    });
  });
}

test("evidence cards open the cited paper passage", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto(WORKSPACE_URL);
  await page.getByRole("button", { name: "Open research copilot" }).click();

  const chat = page.getByRole("dialog", { name: "Research copilot chat" });
  await chat.getByLabel("Copilot message").fill("what did the paper say about the filter?");
  await chat.getByRole("button", { name: "Ask" }).click();

  await expect(chat.getByText("Paper evidence")).toBeVisible();
  await chat.getByRole("button", { name: "Open in paper" }).click();

  await expect(chat.getByText("Page 2 of paper-1")).toBeVisible();
  await expect(chat.getByText("The filter corner is 4 kHz per the paper")).toBeVisible();
});
