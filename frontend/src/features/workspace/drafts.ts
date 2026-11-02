/* Scenario drafts: in-memory op-lists over a base revision. A draft
   collects canvas patches without touching the server; promoting it
   applies the ops as one patch batch, which persists a real revision.
   Drafts never leave memory, so a reload discards them. */

import { create } from "zustand";
import type { GraphPatch } from "../../lib/types.ts";

export interface ScenarioDraft {
  id: string;
  name: string;
  projectId: string;
  graphId: string;
  baseVersion: number;
  baseTitle: string;
  patches: GraphPatch[];
  createdAt: string;
}

interface ScenarioDraftState {
  drafts: ScenarioDraft[];
  activeDraftId: string | null;
  createDraft: (init: {
    name: string;
    projectId: string;
    graphId: string;
    baseVersion: number;
    baseTitle: string;
  }) => ScenarioDraft;
  stagePatches: (id: string, patches: GraphPatch[]) => void;
  removePatch: (id: string, patchId: string) => void;
  deleteDraft: (id: string) => void;
  setActiveDraft: (id: string | null) => void;
  reset: () => void;
}

export function makeDraftId(): string {
  return `draft-${crypto.randomUUID()}`;
}

export function activeDraftForGraph(
  state: ScenarioDraftState,
  projectId: string,
  graphId: string,
): ScenarioDraft | null {
  if (state.activeDraftId === null) return null;
  const draft =
    state.drafts.find((candidate) => candidate.id === state.activeDraftId) ?? null;
  if (draft === null) return null;
  if (draft.projectId !== projectId || draft.graphId !== graphId) return null;
  return draft;
}

export const useScenarioDrafts = create<ScenarioDraftState>()((set) => ({
  drafts: [],
  activeDraftId: null,
  createDraft: (init) => {
    const draft: ScenarioDraft = {
      id: makeDraftId(),
      name: init.name,
      projectId: init.projectId,
      graphId: init.graphId,
      baseVersion: init.baseVersion,
      baseTitle: init.baseTitle,
      patches: [],
      createdAt: new Date().toISOString(),
    };
    set((state) => ({ drafts: [...state.drafts, draft], activeDraftId: draft.id }));
    return draft;
  },
  stagePatches: (id, patches) =>
    set((state) => ({
      drafts: state.drafts.map((draft) =>
        draft.id === id ? { ...draft, patches: [...draft.patches, ...patches] } : draft,
      ),
    })),
  removePatch: (id, patchId) =>
    set((state) => ({
      drafts: state.drafts.map((draft) =>
        draft.id === id
          ? { ...draft, patches: draft.patches.filter((patch) => patch.patch_id !== patchId) }
          : draft,
      ),
    })),
  deleteDraft: (id) =>
    set((state) => ({
      drafts: state.drafts.filter((draft) => draft.id !== id),
      activeDraftId: state.activeDraftId === id ? null : state.activeDraftId,
    })),
  setActiveDraft: (id) => set({ activeDraftId: id }),
  reset: () => set({ drafts: [], activeDraftId: null }),
}));
