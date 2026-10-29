import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useGraphFigures, useIngestGraphFigures } from "../../app/queries.ts";
import { api } from "../../lib/api.ts";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { FigureRegion, PaperFigure } from "../../lib/types.ts";
import styles from "./FigureOverlay.module.css";

function regionStyle(region: FigureRegion): React.CSSProperties {
  const [x, y, width, height] = region.bbox;
  return {
    left: `${x * 100}%`,
    top: `${y * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  };
}

function RegionButton({
  region,
  nodeLabel,
  active,
  onSelect,
}: {
  region: FigureRegion;
  nodeLabel: string | null;
  active: boolean;
  onSelect: (nodeId: string) => void;
}) {
  if (region.node_id === null) {
    return (
      <span
        style={regionStyle(region)}
        className={styles.unlinked}
        title={`${region.label} — depicts no graph node`}
        data-region-id={region.region_id}
      />
    );
  }
  return (
    <button
      type="button"
      style={regionStyle(region)}
      className={`${styles.linked} ${active ? styles.active : ""}`}
      title={`${region.label} → ${nodeLabel ?? region.node_id}`}
      aria-label={`Region ${region.label}, linked to ${nodeLabel ?? region.node_id}`}
      data-region-id={region.region_id}
      data-node-id={region.node_id}
      onClick={() => onSelect(region.node_id as string)}
    />
  );
}

function FigureViewer({
  figure,
  nodeLabels,
  projectId,
  graphId,
}: {
  figure: PaperFigure;
  nodeLabels: Map<string, string>;
  projectId: string;
  graphId: string;
}) {
  const { selectedNodeIds, selectNodes } = useWorkspaceSelection();
  const linked = figure.regions.filter((region) => region.node_id !== null);
  return (
    <div>
      <p className={styles.meta}>
        {figure.label ?? figure.figure_id}
        {figure.page !== null ? ` · page ${figure.page}` : ""}
        {` · ${linked.length} of ${figure.regions.length} regions linked · boxes are approximate`}
        {figure.confidence !== null ? ` · figure confidence ${figure.confidence.toFixed(2)}` : ""}
      </p>
      {figure.caption ? <p className={styles.caption}>{figure.caption}</p> : null}
      <div className={styles.stage}>
        <img
          src={api.figureImageUrl(projectId, graphId, figure.figure_id)}
          alt={figure.caption ?? figure.label ?? figure.figure_id}
          className={styles.image}
        />
        {figure.regions.map((region) => (
          <RegionButton
            key={region.region_id}
            region={region}
            nodeLabel={region.node_id ? (nodeLabels.get(region.node_id) ?? null) : null}
            active={region.node_id !== null && selectedNodeIds.includes(region.node_id)}
            onSelect={(nodeId) => selectNodes([nodeId])}
          />
        ))}
      </div>
      <ul className={styles.regionList}>
        {figure.regions.map((region) => (
          <li key={region.region_id} className={styles.regionRow}>
            <span className={styles.regionLabel}>{region.label}</span>
            {region.node_id !== null ? (
              <button
                type="button"
                className={styles.nodeLink}
                onClick={() => selectNodes([region.node_id as string])}
              >
                {nodeLabels.get(region.node_id) ?? region.node_id}
              </button>
            ) : (
              <span className={styles.unlinkedTag}>unlinked</span>
            )}
            {region.confidence !== null ? (
              <span className={styles.conf}>{region.confidence.toFixed(2)}</span>
            ) : null}
          </li>
        ))}
      </ul>
      {figure.regions.length === 0 ? (
        <p className={styles.hint}>No regions were localized in this figure.</p>
      ) : null}
    </div>
  );
}

function IngestForm({
  projectId,
  graphId,
  version,
}: {
  projectId: string;
  graphId: string;
  version: number;
}) {
  const ingest = useIngestGraphFigures(projectId, graphId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [formError, setFormError] = useState<string | null>(null);

  function submit(event: FormEvent): void {
    event.preventDefault();
    const file = fileRef.current?.files?.[0] ?? null;
    if (!file) {
      setFormError("Choose the paper PDF first.");
      return;
    }
    setFormError(null);
    ingest.mutate({ version, file });
  }

  return (
    <form className={styles.ingest} onSubmit={submit} aria-label="Ingest paper figures">
      <p className={styles.hint}>
        No figures ingested for this graph yet. Upload the paper PDF to locate its
        figures and link their regions to graph nodes.
      </p>
      <div className={styles.ingestRow}>
        <input ref={fileRef} type="file" accept="application/pdf,.pdf" aria-label="Paper PDF" />
        <button type="submit" disabled={ingest.isPending}>
          {ingest.isPending ? "Locating…" : "Locate figures"}
        </button>
      </div>
      {formError ? (
        <p className={styles.formError} role="alert">
          {formError}
        </p>
      ) : null}
      {ingest.isError ? (
        <p className={styles.formError} role="alert">
          Figure ingest failed:{" "}
          {ingest.error instanceof Error ? ingest.error.message : "unknown error"}
        </p>
      ) : null}
      {ingest.isSuccess ? (
        <div className={styles.report} role="status">
          <p>
            Ingested {ingest.data.figures.length}{" "}
            {ingest.data.figures.length === 1 ? "figure" : "figures"}.
            {ingest.data.truncated ? " Figure list truncated at the ingest cap." : ""}
            {ingest.data.skipped > 0 ? ` ${ingest.data.skipped} images skipped.` : ""}
          </p>
          {ingest.data.warnings.length > 0 ? (
            <ul>
              {ingest.data.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

/** Paper-figure overlay: the paper's own figures with clickable
 *  component regions. Linked regions select their graph node, whose
 *  explanation and evidence show in the inspector rail. */
export function FigureOverlay({
  projectId,
  graphId,
  version,
  nodeLabels,
}: {
  projectId: string;
  graphId: string;
  version: number;
  nodeLabels: Map<string, string>;
}) {
  const figures = useGraphFigures(projectId, graphId);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const list = figures.data ?? [];
  // Derived during render: the picked tab, or the first figure. A stale
  // id (figures re-ingested while open) falls back instead of blanking.
  const active = list.find((figure) => figure.figure_id === activeId) ?? list[0] ?? null;

  const count = figures.isSuccess ? list.length : null;
  return (
    <section className={styles.trigger} aria-label="Paper figures">
      <button type="button" onClick={() => setOpen(true)} disabled={figures.isPending}>
        {figures.isPending ? "Paper figures…" : `Paper figures${count !== null ? ` (${count})` : ""}`}
      </button>
      {figures.isError ? (
        <p className={styles.hint}>Figures unavailable for this graph.</p>
      ) : null}
      {open ? (
        <div className={styles.backdrop} onClick={() => setOpen(false)}>
          <div
            className={styles.dialog}
            role="dialog"
            aria-modal="true"
            aria-label="Paper figure overlay"
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.head}>
              <h2>Paper figures</h2>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close figures">
                Close
              </button>
            </div>
            {figures.isPending ? (
              <p className={styles.hint}>Loading figures…</p>
            ) : figures.isError ? (
              <p className={styles.hint}>Figures unavailable for this graph.</p>
            ) : list.length === 0 ? (
              <IngestForm projectId={projectId} graphId={graphId} version={version} />
            ) : (
              <>
                <div className={styles.tabs} role="tablist" aria-label="Figures">
                  {list.map((figure, index) => (
                    <button
                      key={figure.figure_id}
                      type="button"
                      role="tab"
                      aria-selected={active?.figure_id === figure.figure_id}
                      title={figure.label ?? figure.figure_id}
                      onClick={() => setActiveId(figure.figure_id)}
                    >
                      {figure.label ?? `Untitled ${index + 1}`}
                    </button>
                  ))}
                </div>
                {active ? (
                  <FigureViewer
                    figure={active}
                    nodeLabels={nodeLabels}
                    projectId={projectId}
                    graphId={graphId}
                  />
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
