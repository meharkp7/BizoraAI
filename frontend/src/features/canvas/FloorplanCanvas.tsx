import { useMemo } from "react";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type { GraphEntities, MeasuredOverlay, MethodologyGraph } from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import { SymbolGlyph } from "./SymbolGlyph.tsx";
import { arrayDimensions, chipScope, floorplanLayout } from "./chipViews.ts";
import { measuredSummary } from "./flowElements.ts";
import { symbolLabel } from "./graph3d.ts";
import styles from "./FloorplanCanvas.module.css";

function truncate(label: string, max: number): string {
  return label.length > max ? `${label.slice(0, Math.max(max - 1, 0))}…` : label;
}

export function FloorplanCanvas({
  graph,
  entities,
  overlay = EMPTY_OVERLAY,
}: {
  graph: MethodologyGraph;
  entities: GraphEntities | null;
  overlay?: MeasuredOverlay;
}) {
  const scope = useMemo(() => chipScope(graph, entities), [graph, entities]);
  const dims = useMemo(() => arrayDimensions(scope), [scope]);
  const layout = useMemo(
    () => (dims === null ? null : floorplanLayout(scope, dims)),
    [scope, dims],
  );
  const measuredCount = useMemo(() => {
    let count = 0;
    for (const node of scope.graph.nodes) count += overlay.nodes[node.id]?.length ?? 0;
    return count;
  }, [scope, overlay]);
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
  if (dims === null || layout === null) {
    return (
      <div className={styles.empty} role="status">
        <p>No array dimensions in this graph.</p>
        <p className={styles.emptyDetail}>
          The paper states no memory-array geometry, so there is nothing
          honest to lay out — the floorplan stays hidden rather than
          inventing an arrangement.
        </p>
      </div>
    );
  }
  const { items, width, height, downsampled } = layout;
  const sourceLabel =
    scope.graph.nodes.find((node) => node.id === dims.sourceNodeId)?.label ??
    dims.sourceNodeId;
  return (
    <div className={styles.stage}>
      <p className={styles.note} role="note">
        {`${dims.rows}×${dims.columns} array geometry from “${sourceLabel}” (${dims.source}); block sizes and positions are illustrative, not to scale.`}
        {downsampled ? " Array downsampled for display." : null}
        {measuredCount > 0
          ? ` ${measuredCount} measured ${measuredCount === 1 ? "value" : "values"} from run ${overlay.run_id ?? "unknown"}.`
          : null}
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
        {items.map((item, index) => {
          const selected = selectedNodeIds.includes(item.nodeId);
          return (
            <g
              key={`${item.nodeId}-${index}`}
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
                  {item.w >= 20 ? (
                    <g transform={`translate(${(item.w - 20) / 2},${(item.h - 20) / 2})`}>
                      <SymbolGlyph symbol="bitcell" size={20} />
                    </g>
                  ) : null}
                  <title>{`${item.label} (${dims.rows}×${dims.columns} array)`}</title>
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
                  {measuredSummary(overlay.nodes[item.nodeId]) ? (
                    <text x={40} y={54} className={styles.measured}>
                      {truncate(
                        `measured: ${measuredSummary(overlay.nodes[item.nodeId])}`,
                        18,
                      )}
                    </text>
                  ) : null}
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
