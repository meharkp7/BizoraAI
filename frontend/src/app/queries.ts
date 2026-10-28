/* TanStack Query hooks over the Bizora API. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BizoraApiError, api } from "../lib/api.ts";
import type {
  ExperimentConfig,
  GraphLayout,
  GraphPatch,
  GraphPatchBatch,
  PaperUpload,
} from "../lib/types.ts";

export const graphKeys = {
  revision: (projectId: string, graphId: string, version: number) =>
    ["graph", projectId, graphId, "revisions", version] as const,
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
};

export const runKeys = {
  list: (filters?: { project_id?: string; graph_id?: string; limit?: number }) =>
    ["runs", filters ?? {}] as const,
  detail: (runId: string) => ["runs", runId] as const,
  metrics: (runId: string) => ["runs", runId, "metrics"] as const,
  artifacts: (runId: string) => ["runs", runId, "artifacts"] as const,
  comparison: (baselineRunId: string, variantRunId: string) =>
    ["runs", "comparison", baselineRunId, variantRunId] as const,
};

export function useGraphRevision(projectId: string, graphId: string, version: number) {
  return useQuery({
    queryKey: graphKeys.revision(projectId, graphId, version),
    queryFn: () => api.getGraphRevision(projectId, graphId, version),
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
    queryFn: async () => {
      try {
        return await api.getSimulationPreview(projectId, graphId, version);
      } catch (error) {
        // No preview for this revision is normal: the panel stays hidden.
        if (error instanceof BizoraApiError && error.isNotFound) return null;
        throw error;
      }
    },
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

export function useCopilot(projectId: string, graphId: string, version: number) {
  return useMutation({
    mutationFn: ({
      message,
      selectedNodeId,
    }: {
      message: string;
      selectedNodeId: string | null;
    }) => api.askCopilot(projectId, graphId, version, message, selectedNodeId),
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

export const paperKeys = {
  tables: (projectId: string, graphId: string) =>
    ["graph", projectId, graphId, "tables"] as const,
};

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
