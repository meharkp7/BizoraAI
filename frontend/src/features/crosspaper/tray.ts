const STORAGE_KEY = "bizora.crosspaper.tray";

export interface TrayEntry {
  project_id: string;
  graph_id: string;
  title: string;
}

function isTrayEntry(value: unknown): value is TrayEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.project_id === "string" &&
    typeof entry.graph_id === "string" &&
    typeof entry.title === "string"
  );
}

/** Load the persisted tray, dropping corrupt entries. */
export function loadTray(): TrayEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isTrayEntry);
  } catch {
    return [];
  }
}

/** Persist the tray; storage failures keep the in-memory copy only. */
export function saveTray(entries: TrayEntry[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Private mode or quota: the tray still works for this session.
  }
}

export function trayKey(entry: Pick<TrayEntry, "project_id" | "graph_id">): string {
  return `${entry.project_id}::${entry.graph_id}`;
}
