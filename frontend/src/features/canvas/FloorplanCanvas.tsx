import { useMemo } from "react";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MethodologyGraph } from "../../lib/types.ts";
import { SymbolGlyph } from "./CategoryGlyph.tsx";
import { chipScope, floorplanLayout } from "./chipViews.ts";
import { symbolLabel } from "./graph3d.ts";
import styles from "./FloorplanCanvas.module.css";

function truncate(label: string, max: number): string {
  return label.length > max ? `${label.slice(0, Math.max(max - 1, 0))}…` : label;
}

export function FloorplanCanvas({
  graph,
  entities,
}: {
  graph: MethodologyGraph;
  entities: GraphEntities | null;
}) {
  const scope = useMemo(() => chipScope(graph, entities), [graph, entities]);
  const layout = useMemo(() => floorplanLayout(scope), [scope]);
  const { selectedNodeIds, selectNodes } = useWorkspaceSelection();

  if (scope.graph.nodes.length === 0) {
    return (
      <div className={styles.empty} role="status">
        <p>No chip-level entities in this graph.</p>
        <p className={styles.emptyDetail}>
          The floorplan covers electronics designs; nothing here resolved to an
          electronics part.
        </p>
      </div>
    );
  }
  const { items, width, height, columns, rows } = layout;
  const arrayCount = items.filter((item) => item.kind === "cell").length;
  return (
    <div className={styles.stage}>
      <p className={styles.note} role="note">
        Illustrative floorplan: block sizes are not to scale
        {arrayCount > 0
          ? `, and the ${columns}×${rows} bitcell arrangement derives from the node count, not array dimensions.`
          : "."}
        {scope.hiddenCount > 0
          ? ` ${scope.hiddenCount} ${scope.hiddenCount === 1 ? "node" : "nodes"} without an identified electronics part ${scope.hiddenCount === 1 ? "is" : "are"} hidden.`
          : null}
      </p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={styles.sheet}
        role="group"
        aria-label="Array floorplan"
      >
        {items.map((item) => {
          const selected = selectedNodeIds.includes(item.nodeId);
          return (
            <g
              key={item.nodeId}
              transform={`translate(${item.x},${item.y})`}
              data-node-id={item.nodeId}
              data-kind={item.kind}
              data-selected={selected}
              className={styles.node}
              onClick={() => selectNodes([item.nodeId])}
            >
              {item.kind === "cell" ? (
                <>
                  <rect width={item.w} height={item.h} className={styles.cell} />
                  <g transform={`translate(${(item.w - 20) / 2},${(item.h - 20) / 2})`}>
                    <SymbolGlyph symbol="bitcell" size={20} />
                  </g>
                  <title>{`${item.label} (bitcell)`}</title>
                </>
              ) : (
                <>
                  <rect
                    width={item.w}
                    height={item.h}
                    rx={4}
                    className={selected ? styles.blockSelected : styles.block}
                  />
                  <g transform="translate(8,18)">
                    <SymbolGlyph symbol={item.symbol} size={24} />
                  </g>
                  <text x={40} y={26} className={styles.label}>
                    {truncate(item.label, 12)}
                  </text>
                  <text x={40} y={42} className={styles.caption}>
                    {truncate(symbolLabel(item.symbol), 14)}
                  </text>
                </>
              )}
              {selected && item.kind === "cell" ? (
                <rect width={item.w} height={item.h} className={styles.cellSelected} />
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
