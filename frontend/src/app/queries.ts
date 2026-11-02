/* TanStack Query hooks over the Bizora API. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.ts";
import type {
  ExperimentConfig,
  GraphLayout,
  GraphPatch,
  GraphPatchBatch,
  PaperImportRequest,
  PaperUpload,
} from "../lib/types.ts";

export const graphKeys = {
  revision: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version] as const,
  revisionList: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "revisions"] as const,
  layout: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version, "layout"] as const,
  diff: (projectId: string, graphId: string, baseVersion: number, targetVersion: number) =>
    ["graph", projectId, graphId, "diff", baseVersion, targetVersion] as const,
  entities: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version, "entities"] as const,
  preview: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version, "simulation-preview"] as const,
  renderSpecs: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version, "render-specs"] as const,
  figures: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "figures"] as const,
  reportedMetrics: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "reported-metrics"] as const,
};

export const runKeys = {
  list: (filters?: { project_id?: string; graph_id?: string; limit?: number }) =>
    ["runs", filters ?? {}] as const,
  detail: (runId: string) => ["runs", runId] as const,
  metrics: (runId: string) => ["runs", runId, "metrics"] as const,
  artifacts: (runId: string) => ["runs", runId, "artifacts"] as const,
  comparison: (baselineRunId: string, variantRunId: string) =>
    ["runs", "comparison", baselineRunId, variantRunId] as const,
  reportedMetrics: (runId: string, names: readonly string[]) =>
    ["runs", runId, "reported-metrics", ...names] as const,
};

export function useGraphRevision(
  projectId: string,
  graphId: string,
  version: number,
  enabled = true,
) {
  return useQuery({
    queryKey: graphKeys.revision(projectId, graphId, version),
    queryFn: () => api.getGraphRevision(projectId, graphId, version),
    enabled,
  });
}

export function useGraphLayout(projectId: string, graphId: string, version: number) {
  return useQuery({
    queryKey: graphKeys.layout(projectId, graphId, version),
    queryFn: () => api.getLayout(projectId, graphId, version),
    // A missing layout is normal: the canvas falls back to auto-layout.
    retry: false,
  });
}

export function useGraphEntities(projectId: string, graphId: string, version: number) {
  return useQuery({
    queryKey: graphKeys.entities(projectId, graphId, version),
    queryFn: () => api.getGraphEntities(projectId, graphId, version),
  });
}

export function useSimulationPreview(projectId: string, graphId: string, version: number) {
  return useQuery({
    queryKey: graphKeys.preview(projectId, graphId, version),
    // The endpoint returns null for revisions without a preview, so a
    // missing preview never errors; real failures surface to the panel.
    queryFn: () => api.getSimulationPreview(projectId, graphId, version),
    retry: false,
  });
}

export function useSaveLayout(projectId: string, graphId: string, version: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (layout: GraphLayout) => api.saveLayout(layout),
    onSuccess: (layout) => {
      queryClient.setQueryData(graphKeys.layout(projectId, graphId, version), layout);
    },
  });
}

export function useRevisionDiff(
  projectId: string,
  graphId: string,
  baseVersion: number,
  targetVersion: number,
  enabled = true,
) {
  return useQuery({
    queryKey: graphKeys.diff(projectId, graphId, baseVersion, targetVersion),
    queryFn: () => api.diffRevisions(projectId, graphId, baseVersion, targetVersion),
    enabled,
  });
}

export function useRevisionList(projectId: string, graphId: string) {
  return useQuery({
    queryKey: graphKeys.revisionList(projectId, graphId),
    queryFn: () => api.listRevisions(projectId, graphId),
  });
}

export function useRestoreRevision(projectId: string, graphId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ version, requestedBy }: { version: number; requestedBy: string }) =>
      api.restoreRevision(projectId, graphId, version, requestedBy),
    onSuccess: (graph) => {
      queryClient.setQueryData(
        graphKeys.revision(projectId, graphId, graph.version),
        graph,
      );
      queryClient.invalidateQueries({ queryKey: ["graph", projectId, graphId] });
    },
  });
}

export function useApplyPatch(projectId: string, graphId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: GraphPatch) => api.applyPatch(projectId, graphId, patch),
    onSuccess: (graph) => {
      queryClient.setQueryData(
        graphKeys.revision(projectId, graphId, graph.version),
        graph,
      );
      queryClient.invalidateQueries({ queryKey: ["graph", projectId, graphId] });
    },
  });
}

export function useApplyPatchBatch(projectId: string, graphId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (batch: GraphPatchBatch) => api.applyPatchBatch(projectId, graphId, batch),
    onSuccess: (graph) => {
      queryClient.setQueryData(
        graphKeys.revision(projectId, graphId, graph.version),
        graph,
      );
      queryClient.invalidateQueries({ queryKey: ["graph", projectId, graphId] });
    },
  });
}

export function useRuns(filters?: { project_id?: string; graph_id?: string; limit?: number }) {
  return useQuery({
    queryKey: runKeys.list(filters),
    queryFn: () => api.listRuns(filters),
  });
}

export function useRun(runId: string, enabled = true) {
  return useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => api.getRun(runId),
    enabled,
    // Poll active runs; terminal states settle via refetchOnWindowFocus.
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "pending" || state === "running" ? 2000 : false;
    },
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, config }: { runId: string; config: ExperimentConfig }) =>
      api.createRun(runId, config),
    onSuccess: (run) => {
      queryClient.setQueryData(runKeys.detail(run.run_id), run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useExecuteRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.executeRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(runKeys.detail(run.run_id), run);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useRunMetrics(runId: string, enabled = true) {
  return useQuery({
    queryKey: runKeys.metrics(runId),
    queryFn: () => api.listRunMetrics(runId),
    enabled,
  });
}

export function useRunArtifacts(runId: string, enabled = true) {
  return useQuery({
    queryKey: runKeys.artifacts(runId),
    queryFn: () => api.listRunArtifacts(runId),
    enabled,
  });
}

export function useRunComparison(baselineRunId: string, variantRunId: string, enabled = true) {
  return useQuery({
    queryKey: runKeys.comparison(baselineRunId, variantRunId),
    queryFn: () => api.compareRuns(baselineRunId, variantRunId),
    enabled,
  });
}

export function useRunReportedMetrics(runId: string, names: readonly string[], enabled = true) {
  return useQuery({
    queryKey: runKeys.reportedMetrics(runId, names),
    queryFn: () => api.listRunReportedMetrics(runId, [...names]),
    enabled: enabled && names.length > 0,
  });
}

export const componentKeys = {
  list: (filters?: {
    q?: string;
    domain?: string;
    category?: string;
    generic?: boolean;
  }) => ["components", filters ?? {}] as const,
  detail: (componentId: string) => ["components", componentId] as const,
  preflight: (
    projectId: string,
    graphId: string,
    version: number,
    nodeId: string,
    componentId: string,
    config: Record<string, unknown>,
  ) =>
    [
      "graph",
      projectId,
      graphId,
      "revisions",
      version,
      "nodes",
      nodeId,
      "preflight",
      componentId,
      config,
    ] as const,
};

export function useComponentSearch(filters?: {
  q?: string;
  domain?: string;
  category?: string;
  generic?: boolean;
}) {
  return useQuery({
    queryKey: componentKeys.list(filters),
    queryFn: () => api.listComponents(filters),
  });
}

export function useComponentDetail(componentId: string | null) {
  return useQuery({
    queryKey: componentKeys.detail(componentId ?? ""),
    queryFn: () => api.getComponent(componentId ?? ""),
    enabled: componentId !== null,
  });
}

export function usePreflight(
  projectId: string,
  graphId: string,
  version: number,
  nodeId: string | null,
  componentId: string | null,
  config: Record<string, unknown>,
) {
  return useQuery({
    queryKey: componentKeys.preflight(
      projectId,
      graphId,
      version,
      nodeId ?? "",
      componentId ?? "",
      config,
    ),
    queryFn: () =>
      api.preflightReplacement(
        projectId,
        graphId,
        version,
        nodeId ?? "",
        componentId ?? "",
        config,
      ),
    enabled: nodeId !== null && componentId !== null,
    retry: false,
  });
}

export function useRemovalPreflight(
  projectId: string,
  graphId: string,
  version: number,
  nodeId: string | null,
) {
  return useQuery({
    queryKey: [
      "graph",
      projectId,
      graphId,
      "revisions",
      version,
      "nodes",
      nodeId ?? "",
      "removal-preflight",
    ] as const,
    queryFn: () => api.preflightRemoval(projectId, graphId, version, nodeId ?? ""),
    enabled: nodeId !== null,
    retry: false,
  });
}

export function useCopilot(projectId: string, graphId: string, version: number) {
  return useMutation({
    mutationFn: ({
      message,
      selectedNodeId,
      diagramContext,
    }: {
      message: string;
      selectedNodeId: string | null;
      diagramContext: string | null;
    }) => api.askCopilot(projectId, graphId, version, message, selectedNodeId, diagramContext),
  });
}

export const copilotKeys = {
  threads: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "copilot", "threads"] as const,
  thread: (projectId: string, graphId: string, threadId: string) =>
    ["graph", projectId, graphId, "copilot", "threads", threadId] as const,
};

export function useCopilotThreads(projectId: string, graphId: string) {
  return useQuery({
    queryKey: copilotKeys.threads(projectId, graphId),
    queryFn: () => api.listCopilotThreads(projectId, graphId),
  });
}

export function useCopilotThread(
  projectId: string,
  graphId: string,
  threadId: string | null,
) {
  return useQuery({
    queryKey: copilotKeys.thread(projectId, graphId, threadId ?? ""),
    queryFn: () => api.getCopilotThread(projectId, graphId, threadId ?? ""),
    enabled: threadId !== null,
  });
}

export function useGraphs(filters?: { project_id?: string; source_id?: string; limit?: number }) {
  return useQuery({
    queryKey: ["graphs", filters ?? {}] as const,
    queryFn: () => api.listGraphs(filters),
  });
}

export function useArenaComparison(
  a: { project_id: string; graph_id: string } | null,
  b: { project_id: string; graph_id: string } | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["graphs", "compare", a, b] as const,
    queryFn: () => api.compareGraphs(a ?? { project_id: "", graph_id: "" }, b ?? { project_id: "", graph_id: "" }),
    enabled: enabled && a !== null && b !== null,
  });
}

export function usePaperText(sourceId: string, enabled = true) {
  return useQuery({
    queryKey: ["papers", sourceId, "text"] as const,
    queryFn: () => api.getPaperText(sourceId),
    enabled,
    retry: false,
    staleTime: Infinity,
  });
}

export function useCreateCopilotThread(projectId: string, graphId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title: string | null) => api.createCopilotThread(projectId, graphId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: copilotKeys.threads(projectId, graphId) });
    },
  });
}

export function useRenderSpecs(
  projectId: string,
  graphId: string,
  version: number,
  enabled = true,
) {
  return useQuery({
    queryKey: graphKeys.renderSpecs(projectId, graphId, version),
    queryFn: () => api.getRenderSpecs(projectId, graphId, version),
    enabled,
    // A failed specs fetch must never break the explorer: the canvas
    // keeps its archetype placeholders when data is missing.
    retry: false,
  });
}

export function useAdapters() {
  return useQuery({
    queryKey: ["experiments", "adapters"] as const,
    queryFn: () => api.listAdapters(),
  });
}

export function useGraphFigures(projectId: string, graphId: string) {
  return useQuery({
    queryKey: graphKeys.figures(projectId, graphId),
    queryFn: () => api.getGraphFigures(projectId, graphId),
    // Figures are optional enrichment: a missing set never breaks the
    // workspace; the overlay offers an ingest instead.
    retry: false,
  });
}

export function useGraphReportedMetrics(projectId: string, graphId: string) {
  return useQuery({
    queryKey: graphKeys.reportedMetrics(projectId, graphId),
    queryFn: () => api.getGraphReportedMetrics(projectId, graphId),
    // Reported numbers are optional enrichment: tables may be absent.
    retry: false,
  });
}

export function useIngestGraphFigures(projectId: string, graphId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ version, file }: { version: number; file: File }) =>
      api.ingestGraphFigures(projectId, graphId, version, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: graphKeys.figures(projectId, graphId),
      });
    },
  });
}

export const paperKeys = {
  tables: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "tables"] as const,
  diagrams: (paperId: string) => ["papers", paperId, "diagrams"] as const,
  sample: () => ["papers", "sample"] as const,
};

/** Diagram IRs for one paper: the sole feed of the canvas views. */
export function usePaperDiagrams(paperId: string | null) {
  return useQuery({
    queryKey: paperKeys.diagrams(paperId ?? ""),
    queryFn: () => api.getPaperDiagrams(paperId ?? ""),
    enabled: paperId !== null,
  });
}

/** What-if estimate for one methodology step under edited settings. */
export function usePaperWhatIf(paperId: string) {
  return useMutation({
    mutationFn: (input: { nodeId: string; params: Record<string, string> }) =>
      api.runPaperWhatIf(paperId, input.nodeId, input.params),
  });
}

/** Plain-English what-if text resolved to one step plus new settings. */
export function usePaperWhatIfParse(paperId: string) {
  return useMutation({
    mutationFn: (input: { text: string; nodeId: string }) =>
      api.parsePaperWhatIf(paperId, input.text, input.nodeId),
  });
}

/** Configured first-run paper, whether or not it has been seeded yet. */
export function useSamplePaper() {
  return useQuery({
    queryKey: paperKeys.sample(),
    queryFn: () => api.getSamplePaper(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGraphTables(projectId: string, graphId: string) {
  return useQuery({
    queryKey: paperKeys.tables(projectId, graphId),
    queryFn: () => api.listGraphTables(projectId, graphId),
  });
}

export function useExtractPaper() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (upload: PaperUpload) => api.extractPaper(upload),
    onSuccess: (result) => {
      queryClient.setQueryData(
        paperKeys.tables(result.graph.project_id, result.graph.graph_id),
        result.tables,
      );
    },
  });
}

export function useParsePaper() {
  return useMutation({
    mutationFn: (file: File) => api.parsePaper(file),
  });
}

export function useImportPaper() {
  return useMutation({
    mutationFn: (payload: PaperImportRequest) => api.importPaper(payload),
  });
}

export const qualityKeys = {
  summary: () => ["quality", "summary"] as const,
};

/** Last eval runs behind the quality dashboard. */
export function useQualitySummary() {
  return useQuery({
    queryKey: qualityKeys.summary(),
    queryFn: () => api.getQualitySummary(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export const usageKeys = {
  summary: (days: number) => ["usage", "summary", days] as const,
  runs: (limit: number) => ["usage", "runs", limit] as const,
};

/** Estimated spend for the last `days` UTC days. */
export function useUsageSummary(days = 7) {
  return useQuery({
    queryKey: usageKeys.summary(days),
    queryFn: () => api.getUsageSummary(days),
    retry: false,
    staleTime: 60 * 1000,
  });
}

/** Estimated cost per run, most recently used first. */
export function useRunUsage(limit = 50) {
  return useQuery({
    queryKey: usageKeys.runs(limit),
    queryFn: () => api.listRunUsage(limit),
    retry: false,
    staleTime: 60 * 1000,
  });
}

export const accountKeys = {
  me: () => ["account", "me"] as const,
  papers: () => ["account", "papers"] as const,
  notes: (paperId: string) => ["papers", paperId, "notes"] as const,
};

/** The logged-in account, or an error when no token is stored. */
export function useMe(enabled = true) {
  return useQuery({
    queryKey: accountKeys.me(),
    queryFn: () => api.me(),
    enabled,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      api.login(email, password),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.me() });
      void queryClient.invalidateQueries({ queryKey: accountKeys.papers() });
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password, name }: { email: string; password: string; name: string }) =>
      api.register(email, password, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.me() });
      void queryClient.invalidateQueries({ queryKey: accountKeys.papers() });
    },
  });
}

/** The caller's paper library. */
export function useMyPapers(enabled = true) {
  return useQuery({
    queryKey: accountKeys.papers(),
    queryFn: () => api.myPapers(),
    enabled,
    retry: false,
  });
}

/** The caller's notes on one paper. */
export function usePaperNotes(paperId: string | null, enabled = true) {
  return useQuery({
    queryKey: accountKeys.notes(paperId ?? ""),
    queryFn: () => api.listNotes(paperId as string),
    enabled: enabled && paperId !== null,
    retry: false,
  });
}

export function useCreateNote(paperId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api.createNote(paperId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.notes(paperId) });
    },
  });
}

export function useUpdateNote(paperId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, body }: { noteId: number; body: string }) =>
      api.updateNote(paperId, noteId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.notes(paperId) });
    },
  });
}

export function useDeleteNote(paperId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: number) => api.deleteNote(paperId, noteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountKeys.notes(paperId) });
    },
  });
}
