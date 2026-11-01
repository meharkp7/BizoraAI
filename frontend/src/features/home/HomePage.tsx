import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useExtractPaper, useMyPapers, useParsePaper } from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import { useSession } from "../../lib/store.ts";
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
      },
    });
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    if (!file) return;
    extraction.reset();
    extraction.mutate({
      file,
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

function MyPapers() {
  const { token } = useSession();
  const papers = useMyPapers(token !== null);

  if (!token) {
    return (
      <section className={styles.opener} aria-label="My papers">
        <h2>My papers</h2>
        <p className={styles.hint}>
          <Link to="/login">Log in</Link> to keep every paper you upload — your
          library and notes wait under My profile.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.opener} aria-label="My papers">
      <h2>My papers</h2>
      {papers.isPending ? (
        <p className={styles.parseStatus} role="status">
          Loading your papers…
        </p>
      ) : papers.data && papers.data.length > 0 ? (
        <ul className={styles.papers}>
          {papers.data.map((paper) => (
            <li key={`${paper.project_id}/${paper.graph_id}`}>
              <Link
                to={`/g/${encodeURIComponent(paper.project_id)}/${encodeURIComponent(paper.graph_id)}`}
              >
                {paper.title}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.hint}>
          Nothing here yet — upload a paper and it lands here automatically.
        </p>
      )}
    </section>
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
          Any research PDF works: just attach the file and give it a title —
          identifiers are assigned automatically. Logged-in uploads land in your
          library.
        </p>
      </section>
      <MyPapers />
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
