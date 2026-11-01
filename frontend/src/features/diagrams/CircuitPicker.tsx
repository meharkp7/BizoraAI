import type { CircuitIRJson } from "../../lib/types.ts";
import styles from "./DiagramView.module.css";

/** Picks one circuit figure when the endpoint served several. Shared by
 *  the schematic tab and the 3D circuit scene. */
export function CircuitPicker({
  circuits,
  active,
  onPick,
}: {
  circuits: CircuitIRJson[];
  active: number;
  onPick: (index: number) => void;
}) {
  if (circuits.length < 2) return null;
  return (
    <div className={styles.picker} role="tablist" aria-label="Circuits">
      {circuits.map((circuit, index) => (
        <button
          key={`${circuit.source.figure_id}-${index}`}
          type="button"
          role="tab"
          aria-selected={index === Math.min(active, circuits.length - 1)}
          title={`Figure ${circuit.source.figure_id}, page ${circuit.source.page}`}
          onClick={() => onPick(index)}
        >
          {circuit.title}
        </button>
      ))}
    </div>
  );
}
