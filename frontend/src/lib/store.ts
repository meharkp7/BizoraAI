/* Client UI store: theme plus the shared semantic selection that will
   drive both the 2D editor and the 3D explorer. Visual-only state; the
   graph itself always comes from the server. */

import { create } from "zustand";
import type { SandboxItem } from "../features/diagrams/schematicSandbox.ts";
import { clearAuthToken, getAuthToken, setAuthToken } from "./authToken.ts";

export type Theme = "light" | "dark";

interface WorkspaceSelection {
  /** Currently selected node IDs (semantic identity, shared by 2D/3D). */
  selectedNodeIds: string[];
  /** Currently selected edge IDs. */
  selectedEdgeIds: string[];
  selectNodes: (nodeIds: string[]) => void;
  selectEdges: (edgeIds: string[]) => void;
  clearSelection: () => void;
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem("bizora-theme");
  if (stored === "light" || stored === "dark") return stored;
  if (typeof window.matchMedia !== "function") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem("bizora-theme", theme);
}

export const useWorkspaceSelection = create<WorkspaceSelection>()((set) => ({
  selectedNodeIds: [],
  selectedEdgeIds: [],
  selectNodes: (nodeIds) => set({ selectedNodeIds: nodeIds, selectedEdgeIds: [] }),
  selectEdges: (edgeIds) => set({ selectedNodeIds: [], selectedEdgeIds: edgeIds }),
  clearSelection: () => set({ selectedNodeIds: [], selectedEdgeIds: [] }),
}));

export const useTheme = create<ThemeState>()((set) => ({
  theme: initialTheme(),
  setTheme: (theme) => {
    applyTheme(theme);
    set({ theme });
  },
}));

interface SessionState {
  /** JWT Bearer [REDACTED] null when logged out. */
  token: string | null;
  setToken: (token: string) => void;
  clearToken: () => void;
}

export const useSession = create<SessionState>()((set) => ({
  token: typeof window === "undefined" ? null : getAuthToken(),
  setToken: (token) => {
    setAuthToken(token);
    set({ token });
  },
  clearToken: () => {
    clearAuthToken();
    set({ token: null });
  },
}));

export type IndexTab = "graph" | "library";

interface LibrarySelection {
  /** Component id open in the library detail view. */
  selectedComponentId: string | null;
  /** Left-panel tab: the graph index or the component library. */
  indexTab: IndexTab;
  selectComponent: (componentId: string | null) => void;
  setIndexTab: (tab: IndexTab) => void;
  /** Open one library entry, switching to the library tab. */
  openComponent: (componentId: string) => void;
}

export const useLibrarySelection = create<LibrarySelection>()((set) => ({
  selectedComponentId: null,
  indexTab: "graph",
  selectComponent: (componentId) => set({ selectedComponentId: componentId }),
  setIndexTab: (tab) => set({ indexTab: tab }),
  openComponent: (componentId) =>
    set({ selectedComponentId: componentId, indexTab: "library" }),
}));

interface SchematicSandbox {
  /** Library parts on trial, each bound to one schematic figure. */
  items: SandboxItem[];
  /** Figure the schematic tab last showed; trials attach here. */
  activeFigureId: string | null;
  addSandboxItem: (item: SandboxItem) => void;
  removeSandboxItem: (key: string) => void;
  setSandboxPinNet: (key: string, designator: string, netId: string | null) => void;
  setActiveFigure: (figureId: string) => void;
  clearSandboxFigure: (figureId: string) => void;
}

const SANDBOX_STORAGE_KEY = "bizora.sandbox.v1";

function loadSandbox(): Pick<SchematicSandbox, "items" | "activeFigureId"> {
  const empty = { items: [], activeFigureId: null };
  try {
    const raw = window.localStorage.getItem(SANDBOX_STORAGE_KEY);
    if (!raw) return empty;
    const parsed = JSON.parse(raw) as Partial<Pick<SchematicSandbox, "items" | "activeFigureId">>;
    if (!Array.isArray(parsed.items)) return empty;
    const items = parsed.items.filter(
      (item): item is SandboxItem =>
        typeof item?.key === "string" &&
        typeof item?.figureId === "string" &&
        typeof item?.componentId === "string" &&
        typeof item?.label === "string" &&
        typeof item?.engineType === "string" &&
        Array.isArray(item?.pinout) &&
        item.pinout.every((pin) => typeof pin?.designator === "string") &&
        typeof item?.pinNets === "object" &&
        item.pinNets !== null,
    );
    return {
      items,
      activeFigureId: typeof parsed.activeFigureId === "string" ? parsed.activeFigureId : null,
    };
  } catch {
    return empty;
  }
}

export const useSchematicSandbox = create<SchematicSandbox>()((set) => ({
  ...loadSandbox(),
  addSandboxItem: (item) => set((state) => ({ items: [...state.items, item] })),
  removeSandboxItem: (key) =>
    set((state) => ({ items: state.items.filter((item) => item.key !== key) })),
  setSandboxPinNet: (key, designator, netId) =>
    set((state) => ({
      items: state.items.map((item) => {
        if (item.key !== key) return item;
        const pinNets = { ...item.pinNets };
        if (netId === null) delete pinNets[designator];
        else pinNets[designator] = netId;
        return { ...item, pinNets };
      }),
    })),
  setActiveFigure: (figureId) => set({ activeFigureId: figureId }),
  clearSandboxFigure: (figureId) =>
    set((state) => ({ items: state.items.filter((item) => item.figureId !== figureId) })),
}));

// Trials survive refreshes (local-only, per browser).
if (typeof window !== "undefined") {
  useSchematicSandbox.subscribe((state) => {
    try {
      window.localStorage.setItem(
        SANDBOX_STORAGE_KEY,
        JSON.stringify({ items: state.items, activeFigureId: state.activeFigureId }),
      );
    } catch {
      // Private mode: trials just don't persist.
    }
  });
}

/** One methodology step staged for a multi-node what-if run. */
export interface StagedScenarioNode {
  paperId: string;
  nodeId: string;
  nodeLabel: string;
  params: Record<string, string>;
}

interface WhatIfScenario {
  staged: StagedScenarioNode[];
  /** Add or replace one node's staged settings. */
  stageNode: (entry: StagedScenarioNode) => void;
  unstageNode: (paperId: string, nodeId: string) => void;
  clearScenario: (paperId: string) => void;
}

export const useWhatIfScenario = create<WhatIfScenario>()((set) => ({
  staged: [],
  stageNode: (entry) =>
    set((state) => ({
      staged: [
        ...state.staged.filter(
          (staged) => !(staged.paperId === entry.paperId && staged.nodeId === entry.nodeId),
        ),
        entry,
      ],
    })),
  unstageNode: (paperId, nodeId) =>
    set((state) => ({
      staged: state.staged.filter(
        (staged) => !(staged.paperId === paperId && staged.nodeId === nodeId),
      ),
    })),
  clearScenario: (paperId) =>
    set((state) => ({ staged: state.staged.filter((staged) => staged.paperId !== paperId) })),
}));

/** Sync the initial theme to the document on startup. */
export function initTheme(): Theme {
  const theme = initialTheme();
  applyTheme(theme);
  useTheme.setState({ theme });
  return theme;
}
