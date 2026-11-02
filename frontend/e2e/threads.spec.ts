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

const threadList = [
  {
    thread_id: "thread-1",
    title: "Earlier chat",
    turn_count: 2,
    updated_at: "2026-11-01T00:00:00+00:00",
  },
  {
    thread_id: "thread-2",
    title: "Second chat",
    turn_count: 2,
    updated_at: "2026-10-01T00:00:00+00:00",
  },
];

const threadDetails: Record<string, unknown> = {
  "thread-1": {
    thread_id: "thread-1",
    title: "Earlier chat",
    turns: [
      { seq: 0, role: "user", message: "find NPN transistor", response: null },
      {
        seq: 1,
        role: "assistant",
        message: "Closest library matches: 2N3904 NPN transistor.",
        response: {
          reply: "Closest library matches: 2N3904 NPN transistor.",
          cards: [],
          proposal: null,
        },
      },
    ],
  },
  "thread-2": {
    thread_id: "thread-2",
    title: "Second chat",
    turns: [
      { seq: 0, role: "user", message: "compare the options", response: null },
      {
        seq: 1,
        role: "assistant",
        message: "Here is the comparison.",
        response: { reply: "Here is the comparison.", cards: [], proposal: null },
      },
    ],
  },
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
      ],
    });
  });
  await page.route("**/graph-1/copilot/threads", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          thread_id: "thread-3",
          title: "New conversation",
          turn_count: 0,
          updated_at: "2026-11-02T00:00:00+00:00",
        },
      });
      return;
    }
    await route.fulfill({ json: threadList });
  });
  await page.route("**/graph-1/copilot/threads/*", async (route) => {
    const segments = route.request().url().split("/");
    const threadId = segments[segments.length - 1] ?? "thread-1";
    await route.fulfill({ json: threadDetails[threadId] ?? threadDetails["thread-1"] });
  });
}

test("copilot resumes the most recent conversation and switches", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto(WORKSPACE_URL);
  await page.getByRole("button", { name: "Open research copilot" }).click();

  const chat = page.getByRole("dialog", { name: "Research copilot chat" });
  await expect(chat.getByText("find NPN transistor")).toBeVisible();
  await expect(chat.getByText(/Closest library matches/)).toBeVisible();
  await expect(chat.getByLabel("Conversation")).toHaveValue("thread-1");

  await chat.getByLabel("Conversation").selectOption("thread-2");
  await expect(chat.getByText("compare the options")).toBeVisible();
  await expect(chat.getByText("find NPN transistor")).toBeHidden();

  await chat.getByRole("button", { name: "New" }).click();
  await expect(chat.getByLabel("Conversation")).toHaveValue("");
  await expect(chat.getByText("compare the options")).toBeHidden();
});
