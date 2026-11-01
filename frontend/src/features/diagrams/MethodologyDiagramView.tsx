import { useMemo, useState } from "react";
import { dark, light } from "../../diagram-engine/index.js";
import { useTheme } from "../../lib/store.ts";
import type { MethodologyIRJson } from "../../lib/types.ts";
import { renderMethodologyDiagram } from "./adapters.ts";
import { DiagramFallback } from "./DiagramFallback.tsx";
import styles from "./DiagramView.module.css";
import { ScenarioPanel } from "./ScenarioPanel.tsx";
import { ProvenanceLegend, ProvenanceTag } from "./ProvenanceTag.tsx";
import { countProvenance } from "./provenance.ts";
import type { DiagramSelection } from "./selection.ts";
import { methodologySelection } from "./selection.ts";
import { pickSvgId } from "./svgPick.ts";

/** Methodology tab: the paper's flow diagram, rendered by the engine
 *  from the diagrams endpoint. Clicking a node opens the Inspector. */
export function MethodologyDiagramView({
  methodology,
  sourceFigureId,
  warnings,
  projectId,
  graphId,
  paperId,
  nodeLabels,
  onSelect,
}: {
  methodology: MethodologyIRJson | null;
  sourceFigureId: string | null;
  warnings: string[];
  projectId: string;
  graphId: string;
  paperId: string;
  nodeLabels: Map<string, string>;
  onSelect: (selection: DiagramSelection) => void;
}) {
  const theme = useTheme((state) => state.theme);
  // Vertical flow keeps every node at full text size; horizontal chains
  // shrink to fit and turn unreadable, so it stays one click away.
  const [direction, setDirection] = useState<"TB" | "LR">("TB");
  const rendered = useMemo(
    () =>
      methodology === null
        ? null
        : renderMethodologyDiagram(methodology, {
            theme: theme === "dark" ? dark : light,
            direction,
          }),
    [methodology, theme, direction],
  );

  if (methodology === null) {
    return (
      <DiagramFallback
        viewLabel="Methodology"
        reason="the paper's figures yielded nothing suitable."
        sourceFigureId={sourceFigureId}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        warnings={warnings}
      />
    );
  }
  if (rendered === null || !rendered.ok) {
    return (
      <DiagramFallback
        viewLabel="Methodology"
        reason={rendered === null ? "the diagram could not be rendered." : rendered.reason}
        sourceFigureId={sourceFigureId}
        projectId={projectId}
        graphId={graphId}
        nodeLabels={nodeLabels}
        warnings={warnings}
      />
    );
  }

  const counts = countProvenance(methodology.nodes);
  return (
    <div className={styles.view}>
      <div className={styles.head}>
        <h3>{methodology.title}</h3>
        <p className={styles.counts}>
          {counts.fromPaper} from paper · {counts.assumed} assumed
        </p>
      </div>
      <ProvenanceLegend />
      {warnings.length > 0 ? (
        <ul className={styles.warnings} aria-label="Extraction warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      <ScenarioPanel paperId={paperId} />
      <div className={styles.picker} role="group" aria-label="Flow direction">
        <button
          type="button"
          aria-pressed={direction === "TB"}
          onClick={() => setDirection("TB")}
        >
          Vertical
        </button>
        <button
          type="button"
          aria-pressed={direction === "LR"}
          onClick={() => setDirection("LR")}
        >
          Horizontal
        </button>
      </div>
      <div
        className={`${styles.canvas} ${styles.canvasNatural}`}
        role="group"
        aria-label="Methodology diagram"
        dangerouslySetInnerHTML={{ __html: rendered.svg }}
        onClick={(event) => {
          const id = pickSvgId(
            event.currentTarget,
            event.target as Element | null,
            { x: event.clientX, y: event.clientY },
            "data-node-id",
          );
          if (!id) return;
          const node = methodology.nodes.find((entry) => entry.id === id);
          if (node) onSelect(methodologySelection(node));
        }}
      />
      <p className={styles.counts}>
        Dashed nodes are <ProvenanceTag value="assumed" /> — click any node for its
        evidence and editable settings.
      </p>
    </div>
  );
}
