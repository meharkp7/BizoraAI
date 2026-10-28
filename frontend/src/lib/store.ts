/* Client UI store: theme plus the shared semantic selection that will
   drive both the 2D editor and the 3D explorer. Visual-only state; the
   graph itself always comes from the server. */

import { create } from "zustand";

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

/** Sync the initial theme to the document on startup. */
export function initTheme(): Theme {
  const theme = initialTheme();
  applyTheme(theme);
  useTheme.setState({ theme });
  return theme;
}
