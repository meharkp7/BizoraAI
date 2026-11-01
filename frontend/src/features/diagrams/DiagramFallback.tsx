/* Fallback shown when the engine refuses to draw (Safe ok:false) or
   when no IR was extracted: the paper's own figure with clickable
   overlays, plus the reason. Never a placeholder diagram. */

import { useGraphFigures } from "../../app/queries.ts";
import { FigureViewer } from "../figures/FigureOverlay.tsx";
import styles from "./DiagramFallback.module.css";

export function DiagramFallback({
  viewLabel,
  reason,
  sourceFigureId,
  projectId,
  graphId,
  nodeLabels,
  warnings = [],
}: {
  viewLabel: string;
  reason: string;
  /** Preferred figure (the IR's source); falls back to the first. */
  sourceFigureId: string | null;
  projectId: string;
  graphId: string;
  nodeLabels: Map<string, string>;
  warnings?: string[];
}) {
  const figures = useGraphFigures(projectId, graphId);
  const list = figures.data ?? [];
  const figure =
    list.find((entry) => entry.figure_id === sourceFigureId) ?? list[0] ?? null;

  return (
    <div className={styles.fallback} role="group" aria-label={`${viewLabel} fallback`}>
      <p className={styles.reason} role="status">
        No {viewLabel.toLowerCase()} diagram drawn: {reason} Showing the paper&apos;s own
        figure instead.
      </p>
      {warnings.length > 0 ? (
        <ul className={styles.warnings} aria-label="Extraction warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {figures.isPending ? (
        <p className={styles.hint}>Loading the paper&apos;s figures…</p>
      ) : figures.isError || figure === null ? (
        <p className={styles.hint}>
          No figures were ingested for this paper yet. Open “Paper figures” below to
          ingest the PDF; diagrams appear once its figures are extracted.
        </p>
      ) : (
        <FigureViewer
          figure={figure}
          nodeLabels={nodeLabels}
          projectId={projectId}
          graphId={graphId}
        />
      )}
    </div>
  );
}
