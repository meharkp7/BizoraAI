import { useMemo, useState } from "react";
import type {
  GraphEntities,
  GraphLayout,
  MeasuredOverlay,
  MethodologyGraph,
  ViewportState,
} from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import { arrayDimensions, chipScope, schematicSupport } from "./chipViews.ts";
import type { CanvasDiffStatuses } from "./flowElements.ts";
import { FloorplanCanvas } from "./FloorplanCanvas.tsx";
import { GraphCanvas } from "./GraphCanvas.tsx";
import type { LayoutResetRequest } from "./GraphCanvas.tsx";
import type { Point } from "./layout.ts";
import { SchematicCanvas } from "./SchematicCanvas.tsx";
import styles from "./StructureView.module.css";

export type StructureMode = "diagram" | "schematic" | "floorplan";

/** Structure view: the paper's architecture as a block diagram, with
 *  schematic and floorplan as render modes offered only when the
 *  paper supports them (real connections, real array dimensions).
 *  Every mode renders from the graph plus the measured overlay. */
export function StructureView({
  graph,
  layout,
  layoutReset = null,
  diffStatuses,
  entities,
  overlay = EMPTY_OVERLAY,
  mutating,
  onNodesMoved,
  onConnectRequest,
  onDeleteRequest,
}: {
  graph: MethodologyGraph;
  layout: GraphLayout | null;
  layoutReset?: LayoutResetRequest | null;
  diffStatuses: CanvasDiffStatuses | null;
  entities: GraphEntities | null;
  overlay?: MeasuredOverlay;
  mutating?: boolean;
  onNodesMoved?: (positions: Map<string, Point>, viewport: ViewportState) => void;
  onConnectRequest?: (source: string, target: string) => void;
  onDeleteRequest?: (nodeIds: string[], edgeIds: string[]) => void;
}) {
  const scope = useMemo(() => chipScope(graph, entities), [graph, entities]);
  const canSchematic = useMemo(() => schematicSupport(scope), [scope]);
  const dims = useMemo(() => arrayDimensions(scope), [scope]);
  const [mode, setMode] = useState<StructureMode>("diagram");
  const effective: StructureMode =
    mode === "schematic" && !canSchematic
      ? "diagram"
      : mode === "floorplan" && dims === null
        ? "diagram"
        : mode;

  return (
    <div className={styles.view}>
      <div className={styles.modes} role="group" aria-label="Structure mode">
        <button
          type="button"
          onClick={() => setMode("diagram")}
          aria-pressed={effective === "diagram"}
          title="Block diagram: every node, editable"
        >
          Diagram
        </button>
        {canSchematic ? (
          <button
            type="button"
            onClick={() => setMode("schematic")}
            aria-pressed={effective === "schematic"}
            title="Chip schematic: connected electronics parts"
          >
            Schematic
          </button>
        ) : null}
        {dims !== null ? (
          <button
            type="button"
            onClick={() => setMode("floorplan")}
            aria-pressed={effective === "floorplan"}
            title="Array floorplan: stated memory geometry"
          >
            Floorplan
          </button>
        ) : null}
      </div>
      {effective === "schematic" ? (
        <SchematicCanvas
          key={`schematic-${graph.version}`}
          graph={graph}
          entities={entities}
          overlay={overlay}
        />
      ) : effective === "floorplan" ? (
        <FloorplanCanvas
          key={`floorplan-${graph.version}`}
          graph={graph}
          entities={entities}
          overlay={overlay}
        />
      ) : (
        <GraphCanvas
          key={`canvas-${graph.version}`}
          graph={graph}
          layout={layout}
          layoutReset={layoutReset}
          diffStatuses={diffStatuses}
          overlay={overlay}
          mutating={mutating}
          onConnectRequest={onConnectRequest}
          onDeleteRequest={onDeleteRequest}
          onNodesMoved={onNodesMoved}
        />
      )}
    </div>
  );
}
