import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import styles from "./HomePage.module.css";

export function HomePage() {
  const navigate = useNavigate();
  const [projectId, setProjectId] = useState("");
  const [graphId, setGraphId] = useState("");

  function open(event: FormEvent): void {
    event.preventDefault();
    const project = projectId.trim();
    const graph = graphId.trim();
    if (project && graph) {
      void navigate(`/g/${encodeURIComponent(project)}/${encodeURIComponent(graph)}`);
    }
  }

  return (
    <div className={styles.page}>
      <section className={styles.intro}>
        <h1>Evidence-grounded methodology, made testable</h1>
        <p>
          Bizora turns scientific papers into explorable methodology graphs: inspect
          components, trace claims to their sources, propose validated changes, and
          compare measured results against baselines.
        </p>
      </section>
      <section className={styles.opener} aria-label="Open a methodology graph">
        <h2>Open a graph</h2>
        <form className={styles.form} onSubmit={open}>
          <label className={styles.field}>
            Project ID
            <input
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              placeholder="e.g. vit-paper"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <label className={styles.field}>
            Graph ID
            <input
              value={graphId}
              onChange={(event) => setGraphId(event.target.value)}
              placeholder="e.g. vit-base"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <button type="submit" disabled={!projectId.trim() || !graphId.trim()}>
            Open workspace
          </button>
        </form>
        <p className={styles.hint}>
          Graphs are created through the API today; workspace management arrives with
          later phases.
        </p>
      </section>
    </div>
  );
}
