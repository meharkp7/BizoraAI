import { useMemo } from "react";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { SymbolGlyph } from "./CategoryGlyph.tsx";
import { chipScope, schematicBoxes } from "./chipViews.ts";
import type { SchematicBox } from "./chipViews.ts";
import { prettyEntityType, symbolLabel } from "./graph3d.ts";
import styles from "./SchematicCanvas.module.css";

function truncate(label: string, max: number): string {
  return label.length > max ? `${label.slice(0, Math.max(max - 1, 0))}…` : label;
}

function Junction({ x, y }: { x: number; y: number }) {
  return <circle cx={x} cy={y} r={2} className={styles.dot} />;
}

/** Canonical six-transistor SRAM cell in a 224×176 local frame: two
 *  cross-coupled CMOS inverters (PMOS bubbles up, NMOS below) joined by
 *  the Q/QB taps, plus two access FETs on the shared wordline between
 *  the BL/BLB rails. Plain crossings carry no dot and are unconnected,
 *  per modern schematic convention. */
function BitcellCircuit({ label }: { label: string }) {
  return (
    <g className={styles.circuit}>
      <line x1={60} y1={14} x2={164} y2={14} />
      <line x1={60} y1={138} x2={164} y2={138} />
      <text x={168} y={17} className={styles.rail}>
        VDD
      </text>
      <text x={168} y={141} className={styles.rail}>
        VSS
      </text>
      <line x1={30} y1={10} x2={30} y2={148} />
      <line x1={194} y1={10} x2={194} y2={148} />
      <text x={30} y={8} textAnchor="middle" className={styles.rail}>
        BL
      </text>
      <text x={194} y={8} textAnchor="middle" className={styles.rail}>
        BLB
      </text>
      <line x1={20} y1={80} x2={204} y2={80} />
      <text x={206} y={83} className={styles.rail}>
        WL
      </text>
      {/* Left inverter: gates face left, output node Q at x=90. */}
      <line x1={67} y1={32} x2={67} y2={124} />
      <circle cx={64} cy={40} r={2.5} className={styles.bubble} />
      <line x1={75} y1={26} x2={75} y2={54} />
      <line x1={75} y1={102} x2={75} y2={130} />
      <line x1={75} y1={14} x2={75} y2={26} />
      <line x1={75} y1={130} x2={75} y2={138} />
      <line x1={75} y1={50} x2={90} y2={50} />
      <line x1={75} y1={106} x2={90} y2={106} />
      <line x1={90} y1={50} x2={90} y2={106} />
      {/* Right inverter, mirrored: output node QB at x=134. */}
      <line x1={157} y1={32} x2={157} y2={124} />
      <circle cx={160} cy={40} r={2.5} className={styles.bubble} />
      <line x1={149} y1={26} x2={149} y2={54} />
      <line x1={149} y1={102} x2={149} y2={130} />
      <line x1={149} y1={14} x2={149} y2={26} />
      <line x1={149} y1={130} x2={149} y2={138} />
      <line x1={149} y1={50} x2={134} y2={50} />
      <line x1={149} y1={106} x2={134} y2={106} />
      <line x1={134} y1={50} x2={134} y2={106} />
      {/* Cross-coupling taps, crossing the far nodes unconnected. */}
      <line x1={90} y1={70} x2={157} y2={70} />
      <line x1={134} y1={90} x2={67} y2={90} />
      <Junction x={90} y={70} />
      <Junction x={157} y={70} />
      <Junction x={134} y={90} />
      <Junction x={67} y={90} />
      {/* Access FETs between the rails and the storage nodes. */}
      <line x1={55} y1={60} x2={55} y2={100} />
      <line x1={47} y1={68} x2={47} y2={92} />
      <line x1={55} y1={64} x2={30} y2={64} />
      <line x1={55} y1={96} x2={90} y2={96} />
      <line x1={169} y1={60} x2={169} y2={100} />
      <line x1={177} y1={68} x2={177} y2={92} />
      <line x1={169} y1={64} x2={194} y2={64} />
      <line x1={169} y1={96} x2={134} y2={96} />
      <Junction x={30} y={64} />
      <Junction x={90} y={96} />
      <Junction x={194} y={64} />
      <Junction x={134} y={96} />
      <Junction x={47} y={80} />
      <Junction x={177} y={80} />
      <text x={112} y={155} textAnchor="middle" className={styles.label}>
        {truncate(label, 26)}
      </text>
      <text x={112} y={168} textAnchor="middle" className={styles.caption}>
        canonical 6T · illustrative
      </text>
    </g>
  );
}

function CompactSymbol({
  box,
  label,
  entityType,
}: {
  box: SchematicBox;
  label: string;
  entityType: string;
}) {
  if (box.symbol === "generic") {
    return (
      <g>
        <rect
          x={8}
          y={8}
          width={box.w - 16}
          height={box.h - 16}
          rx={4}
          className={styles.genericBox}
        />
        <text x={box.w / 2} y={box.h / 2 - 2} textAnchor="middle" className={styles.label}>
          {truncate(label, 16)}
        </text>
        <text x={box.w / 2} y={box.h / 2 + 14} textAnchor="middle" className={styles.caption}>
          generic placeholder
        </text>
      </g>
    );
  }
  return (
    <g>
      <g transform={`translate(${(box.w - 40) / 2},8)`}>
        <SymbolGlyph symbol={box.symbol} size={40} />
      </g>
      <text x={box.w / 2} y={box.h - 26} textAnchor="middle" className={styles.label}>
        {truncate(label, 16)}
      </text>
      <text x={box.w / 2} y={box.h - 12} textAnchor="middle" className={styles.caption}>
        {truncate(`${symbolLabel(box.symbol)} · ${prettyEntityType(entityType)}`, 24)}
      </text>
    </g>
  );
}

export function SchematicCanvas({
  graph,
  entities,
}: {
  graph: MethodologyGraph;
  entities: GraphEntities | null;
}) {
  const scope = useMemo(() => chipScope(graph, entities), [graph, entities]);
  const { boxes, width, height } = useMemo(() => schematicBoxes(scope), [scope]);
  const { selectedNodeIds, selectNodes } = useWorkspaceSelection();
  const labels = useMemo(
    () => new Map(scope.graph.nodes.map((node) => [node.id, node.label])),
    [scope],
  );
  const centers = useMemo(
    () =>
      new Map(
        boxes.map((box) => [box.nodeId, { x: box.x + box.w / 2, y: box.y + box.h / 2 }]),
      ),
    [boxes],
  );

  if (scope.graph.nodes.length === 0) {
    return (
      <div className={styles.empty} role="status">
        <p>No chip-level entities in this graph.</p>
        <p className={styles.emptyDetail}>
          The schematic covers electronics designs; nothing here resolved to an electronics
          part.
        </p>
      </div>
    );
  }
  return (
    <div className={styles.stage}>
      <p className={styles.note} role="note">
        Layout follows the canvas flow; wiring is illustrative, not a netlist.
        {scope.hiddenCount > 0
          ? ` ${scope.hiddenCount} ${scope.hiddenCount === 1 ? "node" : "nodes"} without an identified electronics part ${scope.hiddenCount === 1 ? "is" : "are"} hidden.`
          : null}
      </p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={styles.sheet}
        role="group"
        aria-label="Chip schematic"
      >
        {scope.graph.edges.map((edge) => {
          const from = centers.get(edge.source);
          const to = centers.get(edge.target);
          if (!from || !to) return null;
          return (
            <line
              key={edge.id}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              className={styles.wire}
            />
          );
        })}
        {boxes.map((box) => {
          const selected = selectedNodeIds.includes(box.nodeId);
          const entityType =
            scope.resolutions.get(box.nodeId)?.entity_type ?? "generic-component";
          return (
            <g
              key={box.nodeId}
              transform={`translate(${box.x},${box.y})`}
              data-node-id={box.nodeId}
              data-selected={selected}
              className={styles.node}
              onClick={() => selectNodes([box.nodeId])}
            >
              {selected ? (
                <rect
                  x={-4}
                  y={-4}
                  width={box.w + 8}
                  height={box.h + 8}
                  rx={6}
                  className={styles.selection}
                />
              ) : null}
              {box.expanded ? (
                <BitcellCircuit label={labels.get(box.nodeId) ?? box.nodeId} />
              ) : (
                <CompactSymbol
                  box={box}
                  label={labels.get(box.nodeId) ?? box.nodeId}
                  entityType={entityType}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
