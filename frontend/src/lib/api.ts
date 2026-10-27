/* Typed client for the Bizora backend API. */

import type {
  ArtifactRecord,
  BizoraErrorBody,
  ExperimentConfig,
  ExperimentRun,
  ExtractedTable,
  GraphEntities,
  GraphLayout,
  GraphPatch,
  GraphPatchBatch,
  GraphRevisionDiff,
  MethodologyGraph,
  MetricRecord,
  PaperExtractionResponse,
  PaperUpload,
  ParsedPaper,
  RunComparison,
} from "./types.ts";

export class BizoraApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.name = "BizoraApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "";
}

function isErrorBody(value: unknown): value is BizoraErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const error = (value as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return false;
  const { code, message } = error as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string";
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${apiBase()}${path}`, init);
  } catch (cause) {
    throw new BizoraApiError(0, "NETWORK_UNREACHABLE", "The Bizora API is unreachable.", {
      cause: String(cause),
    });
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    if (isErrorBody(body)) {
      throw new BizoraApiError(
        response.status,
        body.error.code,
        body.error.message,
        (body.error.details ?? {}) as Record<string, unknown>,
      );
    }
    const detail =
      typeof body === "object" && body !== null
        ? (body as { detail?: unknown }).detail
        : undefined;
    if (typeof detail === "string") {
      // Plain FastAPI HTTPException shape used by some read endpoints.
      const code =
        response.status === 404
          ? "RESOURCE_NOT_FOUND"
          : response.status === 409
            ? "RESOURCE_CONFLICT"
            : response.status === 422
              ? "INVALID_REQUEST"
              : "UNEXPECTED_RESPONSE";
      throw new BizoraApiError(response.status, code, detail, {});
    }
    throw new BizoraApiError(
      response.status,
      "UNEXPECTED_RESPONSE",
      `Request failed with status ${response.status}.`,
      {},
    );
  }

  return body as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  return parse(response);
}

function encode(value: string): string {
  return encodeURIComponent(value);
}

export const api = {
  health(): Promise<{ status: string }> {
    return request("/health");
  },

  getGraphRevision(projectId: string, graphId: string, version: number): Promise<MethodologyGraph> {
    return request(`/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/revisions/${version}`);
  },

  applyPatch(projectId: string, graphId: string, patch: GraphPatch): Promise<MethodologyGraph> {
    return request(`/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/patches`, {
      method: "POST",
      body: JSON.stringify(patch),
    });
  },

  applyPatchBatch(
    projectId: string,
    graphId: string,
    batch: GraphPatchBatch,
  ): Promise<MethodologyGraph> {
    return request(`/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/patch-batches`, {
      method: "POST",
      body: JSON.stringify(batch),
    });
  },

  getLayout(projectId: string, graphId: string, version: number): Promise<GraphLayout> {
    return request(
      `/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/revisions/${version}/layout`,
    );
  },

  getGraphEntities(
    projectId: string,
    graphId: string,
    version: number,
  ): Promise<GraphEntities> {
    return request(
      `/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/revisions/${version}/entities`,
    );
  },

  saveLayout(layout: GraphLayout): Promise<GraphLayout> {
    const { project_id, graph_id, version } = layout;
    return request(
      `/api/v1/graphs/${encode(project_id)}/${encode(graph_id)}/revisions/${version}/layout`,
      { method: "PUT", body: JSON.stringify(layout) },
    );
  },

  diffRevisions(
    projectId: string,
    graphId: string,
    baseVersion: number,
    targetVersion: number,
  ): Promise<GraphRevisionDiff> {
    const params = new URLSearchParams({
      base_version: String(baseVersion),
      target_version: String(targetVersion),
    });
    return request(
      `/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/diff?${params.toString()}`,
    );
  },

  listRuns(filters?: { project_id?: string; graph_id?: string; limit?: number }): Promise<
    ExperimentRun[]
  > {
    const params = new URLSearchParams();
    if (filters?.project_id) params.set("project_id", filters.project_id);
    if (filters?.graph_id) params.set("graph_id", filters.graph_id);
    if (filters?.limit !== undefined) params.set("limit", String(filters.limit));
    const query = params.toString();
    return request(`/api/v1/experiments/runs${query ? `?${query}` : ""}`);
  },

  getRun(runId: string): Promise<ExperimentRun> {
    return request(`/api/v1/experiments/runs/${encode(runId)}`);
  },

  createRun(runId: string, config: ExperimentConfig): Promise<ExperimentRun> {
    return request(`/api/v1/experiments/runs`, {
      method: "POST",
      body: JSON.stringify({ run_id: runId, config }),
    });
  },

  executeRun(runId: string): Promise<ExperimentRun> {
    return request(`/api/v1/experiments/runs/${encode(runId)}/execute`, {
      method: "POST",
    });
  },

  listRunMetrics(runId: string): Promise<MetricRecord[]> {
    return request(`/api/v1/experiments/runs/${encode(runId)}/metrics`);
  },

  listRunArtifacts(runId: string): Promise<ArtifactRecord[]> {
    return request(`/api/v1/experiments/runs/${encode(runId)}/artifacts`);
  },

  compareRuns(baselineRunId: string, variantRunId: string): Promise<RunComparison> {
    const params = new URLSearchParams({
      baseline_run_id: baselineRunId,
      variant_run_id: variantRunId,
    });
    return request(`/api/v1/experiments/comparisons?${params.toString()}`);
  },

  parsePaper(file: File): Promise<ParsedPaper> {
    const form = new FormData();
    form.set("file", file);
    // No JSON content type: the browser sets the multipart boundary.
    return send("/api/v1/papers/parse", { method: "POST", body: form }).then((response) =>
      parse<ParsedPaper>(response),
    );
  },

  extractPaper(upload: PaperUpload): Promise<PaperExtractionResponse> {
    const form = new FormData();
    form.set("file", upload.file);
    if (upload.project_id) form.set("project_id", upload.project_id);
    if (upload.graph_id) form.set("graph_id", upload.graph_id);
    if (upload.source_id) form.set("source_id", upload.source_id);
    if (upload.created_by) form.set("created_by", upload.created_by);
    if (upload.title) form.set("title", upload.title);
    // No JSON content type: the browser sets the multipart boundary.
    return send("/api/v1/papers/extract", { method: "POST", body: form }).then((response) =>
      parse<PaperExtractionResponse>(response),
    );
  },

  listGraphTables(projectId: string, graphId: string): Promise<ExtractedTable[]> {
    return request(`/api/v1/graphs/${encode(projectId)}/${encode(graphId)}/tables`);
  },
};
