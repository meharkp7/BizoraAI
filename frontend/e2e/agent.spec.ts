import { expect, test, type Page } from "@playwright/test";

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

const history = [
  {
    version: 1,
    parent_version: null,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    version: 2,
    parent_version: 1,
    title: "Vision transformer",
    created_by: "test",
    created_at: "2026-01-02T00:00:00Z",
  },
];

async function stubAgentData(page: Page) {
  await page.route("**/api/v1/graphs/project-1/graph-1/revisions", async (route) => {
    await route.fulfill({ json: history });
  });
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
      reply: "The encoder has twelve layers.",
      cards: [],
      proposal: null,
    };
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ response })}\n\n`,
    });
  });
}

test("the workspace shows exactly one agent", async ({ page }) => {
  await stubAgentData(page);
  await page.goto("/g/project-1/graph-1");

  await expect(page.getByRole("button", { name: "Open Bizora agent" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Bizora agent" })).toHaveCount(1);
});

test("the agent chats from a graph sub-page", async ({ page }) => {
  await stubAgentData(page);
  await page.route("**/api/v1/experiments/runs", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/v1/papers/*/notes", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/g/project-1/graph-1/notebook");
  await expect(page.getByRole("heading", { name: "Notebook" })).toBeVisible();

  await page.getByRole("button", { name: "Open Bizora agent" }).click();
  const chat = page.getByRole("dialog", { name: "Bizora agent chat" });
  await expect(chat.getByText(/Chatting about/)).toBeVisible();

  await chat.getByLabel("Agent message").fill("how many layers?");
  await chat.getByRole("button", { name: "Ask" }).click();
  await expect(chat.getByText("The encoder has twelve layers.")).toBeVisible();
});

test("the agent follows the recent graph onto plain pages", async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.localStorage.setItem(
      "bizora.siteAgent.graph",
      JSON.stringify({ projectId: "project-1", graphId: "graph-1" }),
    );
    globalThis.localStorage.setItem("bizora.auth.token", "test-token");
  });
  await stubAgentData(page);
  await page.route("**/api/v1/papers/sample", async (route) => {
    await route.fulfill({
      json: {
        project_id: "project-1",
        graph_id: "graph-1",
        source_id: "paper-1",
        title: "Sample",
        workspace_path: "/g/project-1/graph-1",
        available: false,
      },
    });
  });
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      json: {
        user_id: "user-1",
        email: "me@example.com",
        name: "Me",
        created_at: "2026-01-01T00:00:00+00:00",
      },
    });
  });
  await page.route("**/api/v1/users/me/papers", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/papers");
  await page.getByRole("button", { name: "Open Bizora agent" }).click();

  const chat = page.getByRole("dialog", { name: "Bizora agent chat" });
  await expect(chat.getByText(/Chatting about/)).toBeVisible();
  await chat.getByLabel("Agent message").fill("how many layers?");
  await chat.getByRole("button", { name: "Ask" }).click();
  await expect(chat.getByText("The encoder has twelve layers.")).toBeVisible();
});
