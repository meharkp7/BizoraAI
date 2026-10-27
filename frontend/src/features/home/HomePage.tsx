import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useNavigate } from "react-router";
import { useExtractPaper, useParsePaper } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import styles from "./HomePage.module.css";

function filenameStem(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? name;
  return base.replace(/\.pdf$/i, "") || "paper";
}

function UploadForm() {
  const navigate = useNavigate();
  const parsing = useParsePaper();
  const extraction = useExtractPaper();
  const [file, setFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState("");
  const [graphId, setGraphId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [author, setAuthor] = useState("");
  const [title, setTitle] = useState("");

  function onFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const [selected] = event.target.files ?? [];
    if (!selected) {
      setFile(null);
      return;
    }
    setFile(selected);
    extraction.reset();
    parsing.mutate(selected, {
      onSuccess: (parsed) => {
        setTitle(parsed.title ?? filenameStem(parsed.filename));
        setProjectId(parsed.suggested.project_id);
        setGraphId(parsed.suggested.graph_id);
        setSourceId(parsed.suggested.source_id);
      },
    });
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!file) return;
    extraction.reset();
    extraction.mutate({
      file,
      project_id: projectId.trim() === "" ? undefined : projectId.trim(),
      graph_id: graphId.trim() === "" ? undefined : graphId.trim(),
      source_id: sourceId.trim() === "" ? undefined : sourceId.trim(),
      created_by: author.trim() === "" ? undefined : author.trim(),
      title: title.trim() === "" ? undefined : title.trim(),
    });
  }

  const busy = parsing.isPending || extraction.isPending;
  const parsed = parsing.data ?? null;
  const error = parsing.error ?? extraction.error;
  const result = extraction.data ?? null;

  return (
    <div>
      <form className={styles.form} onSubmit={submit} aria-label="Upload a paper">
        <label className={styles.field}>
          Paper (PDF)
          <input type="file" accept=".pdf,application/pdf" onChange={onFileChange} />
        </label>
        {parsing.isPending ? (
          <p className={styles.parseStatus} role="status">
            Reading paper…
          </p>
        ) : null}
        {parsed ? (
          <p className={styles.parseStatus} role="status">
            {parsed.page_count} page(s)
            {parsed.authors.length > 0 ? ` · ${parsed.authors.join("; ")}` : ""}
            {parsed.truncated ? " · text truncated" : ""}
          </p>
        ) : null}
        <label className={styles.field}>
          Title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Read from the paper when available"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className={styles.field}>
          Project ID (optional)
          <input
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            placeholder="Suggested automatically"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className={styles.field}>
          Graph ID (optional)
          <input
            value={graphId}
            onChange={(event) => setGraphId(event.target.value)}
            placeholder="Suggested automatically"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className={styles.field}>
          Source ID (optional)
          <input
            value={sourceId}
            onChange={(event) => setSourceId(event.target.value)}
            placeholder="Suggested automatically"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className={styles.field}>
          Author (optional)
          <input
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
            placeholder="Defaults to paper-upload"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <button type="submit" disabled={file === null || busy}>
          {extraction.isPending ? "Extracting paper…" : "Upload and extract"}
        </button>
      </form>
      {error ? (
        <p className={styles.formError} role="alert">
          {error instanceof BizoraApiError
            ? `Paper processing failed (${error.code}). ${error.message}`
            : "Paper processing failed."}
        </p>
      ) : null}
      {result ? (
        <div className={styles.result} role="status">
          <p>
            Extracted <strong>{result.graph.title}</strong>: revision{" "}
            {result.graph.version} with {result.graph.nodes.length} component(s) and{" "}
            {result.tables.length} table(s) from {result.page_count} page(s).
          </p>
          {result.warnings.length > 0 ? (
            <ul className={styles.warnings}>
              {result.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            onClick={() =>
              void navigate(
                `/g/${encodeURIComponent(result.graph.project_id)}/${encodeURIComponent(result.graph.graph_id)}`,
              )
            }
          >
            Open workspace
          </button>
        </div>
      ) : null}
    </div>
  );
}

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
      <section className={styles.opener} aria-label="Upload a paper">
        <h2>Upload a paper</h2>
        <UploadForm />
        <p className={styles.hint}>
          Any research PDF works: identifiers are suggested from the file and can be
          edited. The methodology graph plus results tables appear in the workspace.
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
              placeholder="e.g. paper-project"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <label className={styles.field}>
            Graph ID
            <input
              value={graphId}
              onChange={(event) => setGraphId(event.target.value)}
              placeholder="e.g. paper-graph"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <button type="submit" disabled={!projectId.trim() || !graphId.trim()}>
            Open workspace
          </button>
        </form>
      </section>
    </div>
  );
}
