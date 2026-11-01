import type { CanvasView } from "../../app/routeElements.tsx";
import styles from "./CanvasToolbar.module.css";

/** Canvas toolbar: the three diagram views. The views render paper
 *  diagrams read-only, so no editing controls live here; graph edits
 *  go through the Inspector and the copilot. */
export function CanvasToolbar({
  view,
  onViewChange,
  disabled,
}: {
  view: CanvasView;
  onViewChange: (view: CanvasView) => void;
  disabled?: boolean;
}) {
  return (
    <div className={styles.toolbar}>
      <div className={styles.viewToggle} role="group" aria-label="Canvas view">
        <button
          type="button"
          onClick={() => onViewChange("methodology")}
          disabled={disabled}
          aria-pressed={view === "methodology"}
          title="Methodology: the paper's flow diagram"
        >
          Methodology
        </button>
        <button
          type="button"
          onClick={() => onViewChange("schematic")}
          disabled={disabled}
          aria-pressed={view === "schematic"}
          title="Schematic: the paper's circuit figures"
        >
          Schematic
        </button>
        <button
          type="button"
          onClick={() => onViewChange("3d")}
          disabled={disabled}
          aria-pressed={view === "3d"}
          title="3D structure: the paper's physical build"
        >
          3D
        </button>
      </div>
    </div>
  );
}
