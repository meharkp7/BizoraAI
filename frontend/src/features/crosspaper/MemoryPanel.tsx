import { useState } from "react";
import type { FormEvent } from "react";
import {
  useCreateMemoryFact,
  useDeleteMemoryFact,
  useProjectMemory,
} from "../../app/queries.ts";
import { CROSS_PAPER_ACTOR } from "../../lib/constants.ts";
import { EmptyState, ErrorState, LoadingState } from "../../components/states.tsx";
import styles from "./CrossPaperPage.module.css";
import type { TrayEntry } from "./tray.ts";

function projectIdsOf(tray: TrayEntry[]): string[] {
  return Array.from(new Set(tray.map((entry) => entry.project_id))).sort();
}

function MemoryFacts({ projectId }: { projectId: string }) {
  const facts = useProjectMemory(projectId);
  const create = useCreateMemoryFact(projectId);
  const remove = useDeleteMemoryFact(projectId);
  const [draft, setDraft] = useState("");

  function submit(event: FormEvent): void {
    event.preventDefault();
    const fact = draft.trim();
    if (!fact || create.isPending) return;
    create.mutate(
      { fact, createdBy: CROSS_PAPER_ACTOR },
      { onSuccess: () => setDraft("") },
    );
  }

  if (facts.isPending) return <LoadingState label="Loading memory…" />;
  if (facts.isError || !facts.data) {
    return (
      <ErrorState
        title="Could not load memory."
        detail={facts.error instanceof Error ? facts.error.message : undefined}
        onRetry={() => void facts.refetch()}
      />
    );
  }

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} onSubmit={submit} aria-label="Remember a fact">
        <label>
          New fact
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="The tapeout uses 65nm…"
            maxLength={500}
            aria-label="Memory fact"
          />
        </label>
        <button type="submit" disabled={create.isPending || draft.trim() === ""}>
          {create.isPending ? "…" : "Remember"}
        </button>
      </form>

      {facts.data.length === 0 ? (
        <EmptyState
          title="Nothing remembered yet."
          detail='Store facts here or tell the copilot "remember ...".'
        />
      ) : (
        <ul className={styles.plain}>
          {facts.data.map((entry) => (
            <li key={entry.id} className={styles.memoryRow}>
              <span>{entry.fact}</span>
              <span className={styles.meta}>by {entry.created_by}</span>
              <button
                type="button"
                disabled={remove.isPending}
                onClick={() => remove.mutate(entry.id)}
                aria-label={`Forget: ${entry.fact}`}
              >
                Forget
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MemoryPanel({ tray }: { tray: TrayEntry[] }) {
  const projects = projectIdsOf(tray);
  const [projectId, setProjectId] = useState<string>("");

  if (projects.length === 0) {
    return (
      <EmptyState
        title="Add a graph to the tray to open its project memory."
        detail="Memory belongs to a project, so every paper in it shares the facts."
      />
    );
  }
  const active = projectId || projects[0]!;

  return (
    <div className={styles.arena}>
      <form className={styles.arenaForm} aria-label="Pick memory project">
        <label>
          Project
          <select value={active} onChange={(event) => setProjectId(event.target.value)}>
            {projects.map((project) => (
              <option key={project} value={project}>
                {project}
              </option>
            ))}
          </select>
        </label>
      </form>
      <MemoryFacts key={active} projectId={active} />
    </div>
  );
}
