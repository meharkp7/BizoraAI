import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import {
  useExtractPaper,
  useImportPaper,
  useMyPapers,
  useParsePaper,
  useSamplePaper,
} from "../../app/queries.ts";
import { BizoraApiError } from "../../lib/api.ts";
import type { PaperExtractionResponse, ParsedPaper } from "../../lib/types.ts";
import { useSession } from "../../lib/store.ts";
import styles from "./PapersPage.module.css";

function filenameStem(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? name;
  return base.replace(/\.pdf$/i, "") || "paper";
}

type UploadStatus = "reading" | "ready" | "extracting" | "done" | "failed";

interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  title: string;
  parsed: ParsedPaper | null;
  result: PaperExtractionResponse | null;
  error: unknown;
}

function errorMessage(error: unknown): string {
  if (error instanceof BizoraApiError) {
    return `Paper processing failed (${error.code}). ${error.message}`;
  }
  return "Paper processing failed.";
}

function uploadStatusText(status: UploadStatus): string {
  switch (status) {
    case "reading":
      return "Reading paper…";
    case "ready":
      return "Ready to extract";
    case "extracting":
      return "Extracting paper…";
    case "done":
      return "Extracted";
    case "failed":
      return "Failed";
  }
}

function UploadForm() {
  const navigate = useNavigate();
  const parsing = useParsePaper();
  const extraction = useExtractPaper();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const nextId = useRef(0);
  const itemsRef = useRef<UploadItem[]>([]);
  const pendingParses = useRef(new Map<string, Promise<void>>());

  function updateItems(updater: (prev: UploadItem[]) => UploadItem[]): void {
    setItems((prev) => {
      const next = updater(prev);
      itemsRef.current = next;
      return next;
    });
  }

  function patchItem(id: string, patch: Partial<UploadItem>): void {
    updateItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    );
  }

  async function runParse(id: string, file: File): Promise<void> {
    try {
      const parsed = await parsing.mutateAsync(file);
      patchItem(id, {
        status: "ready",
        parsed,
        title: parsed.title ?? filenameStem(parsed.filename),
      });
    } catch (error) {
      patchItem(id, { status: "failed", error });
    }
  }

  function ensureParsed(id: string, file: File): Promise<void> {
    const pending = pendingParses.current.get(id);
    if (pending) return pending;
    const started = runParse(id, file).finally(() => {
      pendingParses.current.delete(id);
    });
    pendingParses.current.set(id, started);
    return started;
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>): void {
    const selected = Array.from(event.target.files ?? []);
    if (selected.length === 0) return;
    const fresh: UploadItem[] = selected.map((file) => {
      nextId.current += 1;
      return {
        id: `upload-${nextId.current}`,
        file,
        status: "reading",
        title: "",
        parsed: null,
        result: null,
        error: null,
      };
    });
    updateItems((prev) => [...prev, ...fresh]);
    for (const item of fresh) void ensureParsed(item.id, item.file);
    event.target.value = "";
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (submitting || items.length === 0) return;
    setSubmitting(true);
    try {
      const queued = items.filter(
        (item) => item.status === "reading" || item.status === "ready",
      );
      for (const queuedItem of queued) {
        await ensureParsed(queuedItem.id, queuedItem.file);
        const current = itemsRef.current.find((item) => item.id === queuedItem.id);
        if (!current || current.status !== "ready") continue;
        patchItem(current.id, { status: "extracting", error: null });
        try {
          const result = await extraction.mutateAsync({
            file: current.file,
            title: current.title.trim() === "" ? undefined : current.title.trim(),
          });
          patchItem(current.id, { status: "done", result });
        } catch (error) {
          patchItem(current.id, { status: "failed", error });
        }
      }
    } finally {
      setSubmitting(false);
    }
  }

  const doneCount = items.filter((item) => item.status === "done").length;

  return (
    <div>
      <form
        className={styles.form}
        onSubmit={(event) => void submit(event)}
        aria-label="Upload a paper"
      >
        <label className={styles.field}>
          Paper (PDF)
          <input
            type="file"
            accept=".pdf,application/pdf"
            multiple
            onChange={onFileChange}
          />
        </label>
        {items.length > 0 ? (
          <p className={styles.parseStatus} role="status">
            {doneCount} of {items.length} extracted
          </p>
        ) : null}
        <ul className={styles.queue}>
          {items.map((item) => (
            <li key={item.id}>
              <fieldset className={styles.queueItem}>
                <legend>{item.file.name}</legend>
                <p className={styles.parseStatus} role="status">
                  {uploadStatusText(item.status)}
                </p>
                {item.parsed ? (
                  <p className={styles.parseStatus}>
                    {item.parsed.page_count} page(s)
                    {item.parsed.authors.length > 0
                      ? ` · ${item.parsed.authors.join("; ")}`
                      : ""}
                    {item.parsed.truncated ? " · text truncated" : ""}
                  </p>
                ) : null}
                {item.parsed?.duplicate_of ? (
                  <p className={styles.duplicate}>
                    Already extracted as{" "}
                    <strong>{item.parsed.duplicate_of.title}</strong>.{" "}
                    <Link to={item.parsed.duplicate_of.workspace_path}>
                      Open existing workspace
                    </Link>
                  </p>
                ) : null}
                <label className={styles.field}>
                  Title
                  <input
                    value={item.title}
                    onChange={(event) =>
                      patchItem(item.id, { title: event.target.value })
                    }
                    placeholder="Read from the paper when available"
                    autoComplete="off"
                    spellCheck={false}
                    disabled={
                      submitting ||
                      item.status === "reading" ||
                      item.status === "extracting"
                    }
                  />
                </label>
                {item.status === "failed" && item.error ? (
                  <p className={styles.formError} role="alert">
                    {errorMessage(item.error)}
                  </p>
                ) : null}
                {item.status === "done" && item.result ? (
                  <div className={styles.result} role="status">
                    <p>
                      Extracted <strong>{item.result.graph.title}</strong>: revision{" "}
                      {item.result.graph.version} with{" "}
                      {item.result.graph.nodes.length} component(s) and{" "}
                      {item.result.tables.length} table(s) from{" "}
                      {item.result.page_count} page(s).
                    </p>
                    {item.result.warnings.length > 0 ? (
                      <ul className={styles.warnings}>
                        {item.result.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    ) : null}
                    <button
                      type="button"
                      className="bz-btn bz-btn-primary"
                      onClick={() =>
                        void navigate(
                          `/g/${encodeURIComponent(item.result?.graph.project_id ?? "")}/${encodeURIComponent(item.result?.graph.graph_id ?? "")}`,
                        )
                      }
                    >
                      Open workspace
                    </button>
                  </div>
                ) : null}
              </fieldset>
            </li>
          ))}
        </ul>
        <button
          type="submit"
          className="bz-btn bz-btn-primary"
          disabled={items.length === 0 || submitting}
        >
          {submitting ? "Extracting papers…" : "Upload and extract"}
        </button>
      </form>
    </div>
  );
}

function ImportForm() {
  const navigate = useNavigate();
  const importing = useImportPaper();
  const [source, setSource] = useState("");
  const [title, setTitle] = useState("");

  function submit(event: FormEvent): void {
    event.preventDefault();
    const trimmed = source.trim();
    if (trimmed === "" || importing.isPending) return;
    importing.mutate({
      source: trimmed,
      title: title.trim() === "" ? undefined : title.trim(),
    });
  }

  const result = importing.data ?? null;
  const error = importing.error ?? null;

  return (
    <div>
      <form
        className={styles.form}
        onSubmit={submit}
        aria-label="Import a paper from a link"
      >
        <label className={styles.field}>
          ArXiv ID, DOI, or URL
          <input
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder="e.g. 1706.03762v7"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className={styles.field}>
          Title (optional)
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Read from the paper when available"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <button
          type="submit"
          className="bz-btn bz-btn-primary"
          disabled={source.trim() === "" || importing.isPending}
        >
          {importing.isPending ? "Importing paper…" : "Import and extract"}
        </button>
      </form>
      {error ? (
        <p className={styles.formError} role="alert">
          {errorMessage(error)}
        </p>
      ) : null}
      {result ? (
        <div className={styles.result} role="status">
          <p>
            Imported from {result.source_url}: extracted{" "}
            <strong>{result.extraction.graph.title}</strong> with{" "}
            {result.extraction.tables.length} table(s) from{" "}
            {result.extraction.page_count} page(s).
          </p>
          {result.extraction.warnings.length > 0 ? (
            <ul className={styles.warnings}>
              {result.extraction.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            className="bz-btn bz-btn-primary"
            onClick={() =>
              void navigate(
                `/g/${encodeURIComponent(result.extraction.graph.project_id)}/${encodeURIComponent(result.extraction.graph.graph_id)}`,
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

function SamplePaper() {
  const sample = useSamplePaper();

  return (
    <section className={`${styles.opener} ${styles.sample}`} aria-label="Sample paper">
      <h2>Sample paper</h2>
      {sample.isPending ? (
        <p className={styles.parseStatus} role="status">
          Loading the sample paper…
        </p>
      ) : sample.isError || !sample.data ? (
        <p className={styles.hint}>The sample paper is unavailable right now.</p>
      ) : sample.data.available ? (
        <>
          <p className={styles.hint}>
            Start here: a complete workspace with no upload or setup.
          </p>
          <Link
            className={`bz-btn bz-btn-primary ${styles.sampleLink}`}
            to={sample.data.workspace_path}
          >
            Open the sample paper: {sample.data.title}
          </Link>
        </>
      ) : (
        <p className={styles.hint}>
          The sample paper is not seeded yet. Run{" "}
          <code className={styles.command}>scripts/seed_sample_paper.py</code>, then reload
          this page.
        </p>
      )}
    </section>
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

export function PapersPage() {
  return (
    <div className={`bz-page bz-wide bz-enter ${styles.page}`}>
      <section className={styles.intro}>
        <p className={styles.kicker}>
          <span className={styles.rule} aria-hidden="true" />
          Your library
        </p>
        <h1>Evidence-grounded methodology, made testable</h1>
        <p>
          Bizora turns scientific papers into explorable methodology graphs: inspect
          components, trace claims to their sources, propose validated changes, and
          compare measured results against baselines.
        </p>
      </section>
      <SamplePaper />
      <div className={styles.intake}>
        <section className={styles.opener} aria-label="Upload a paper">
          <h2>Upload a paper</h2>
          <UploadForm />
          <p className={styles.hint}>
            Attach one or several research PDFs; each is read, then extracted in
            turn. Identifiers are assigned automatically, and logged-in uploads
            land in your library.
          </p>
        </section>
        <section className={styles.opener} aria-label="Import a paper">
          <h2>Import a paper</h2>
          <ImportForm />
          <p className={styles.hint}>
            Paste an arXiv ID, DOI, or direct PDF link — Bizora downloads and
            extracts it exactly like an upload.
          </p>
        </section>
      </div>
      <MyPapers />
    </div>
  );
}
