import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CanvasView } from "../../app/routeElements.tsx";
import type {
  CopilotDiagramElement,
  CopilotDiagramRef,
  GraphPatch,
  MethodologyGraph,
} from "../../lib/types.ts";
import type { DiagramSelection } from "../diagrams/selection.ts";
import { CopilotPanel } from "./CopilotPanel.tsx";
import styles from "./CopilotBot.module.css";

const STORAGE_KEY = "bizora.copilotBot";
const DRAG_THRESHOLD_PX = 4;

interface Position {
  x: number;
  y: number;
}

function loadPosition(): Position | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Position>;
    if (typeof parsed.x === "number" && typeof parsed.y === "number") {
      return { x: parsed.x, y: parsed.y };
    }
  } catch {
    // Corrupt or unavailable storage: default spot.
  }
  return null;
}

function RobotFace(): ReactNode {
  return (
    <svg viewBox="0 0 36 36" className={styles.face} aria-hidden="true">
      <line x1="18" y1="2.5" x2="18" y2="8" className={styles.stroke} strokeWidth="2" />
      <circle cx="18" cy="4" r="2.2" className={styles.antennaDot} />
      <line x1="4" y1="15" x2="8" y2="16.5" className={styles.stroke} strokeWidth="2.4" />
      <line x1="32" y1="15" x2="28" y2="16.5" className={styles.stroke} strokeWidth="2.4" />
      <rect x="7" y="9" width="22" height="19" rx="7" className={styles.head} />
      <g className={styles.eyes}>
        <circle cx="13.5" cy="17" r="2.6" className={styles.dot} />
        <circle cx="22.5" cy="17" r="2.6" className={styles.dot} />
      </g>
      <circle cx="11" cy="21.5" r="1.8" className={styles.cheek} />
      <circle cx="25" cy="21.5" r="1.8" className={styles.cheek} />
      <path d="M14 21.5 Q18 24.5 22 21.5" className={styles.smile} strokeWidth="2" fill="none" />
    </svg>
  );
}

/** Floating research copilot: a draggable robot that opens the chat in
 *  an overlay. The conversation itself is the existing CopilotPanel,
 *  so turns, evidence cards, and approval-gated proposals work
 *  unchanged; only the entry point floats. */
export function CopilotBot({
  projectId,
  graph,
  disabled,
  view,
  selection,
  diagramElements = [],
  onSubmit,
  onSelectDiagram = null,
}: {
  projectId: string;
  graph: MethodologyGraph;
  disabled: boolean;
  view: CanvasView;
  selection: DiagramSelection | null;
  diagramElements?: CopilotDiagramElement[];
  onSubmit: (patches: GraphPatch[]) => void;
  onSelectDiagram?: ((ref: CopilotDiagramRef) => void) | null;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Position | null>(() =>
    typeof window === "undefined" ? null : loadPosition(),
  );
  const drag = useRef<{
    dx: number;
    dy: number;
    downX: number;
    downY: number;
    moved: boolean;
  } | null>(null);
  // A drag that travels also fires click: set on pointer-up, consumed
  // once by the click handler (pointer-up runs first, so the drag ref
  // itself cannot carry this).
  const suppressClick = useRef(false);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open ]);

  function clamp(position: Position): Position {
    const margin = 8;
    const size = 56;
    return {
      x: Math.min(Math.max(position.x, margin), window.innerWidth - size - margin),
      y: Math.min(Math.max(position.y, margin), window.innerHeight - size - margin),
    };
  }

  return (
    <>
      <button
        type="button"
        className={styles.bot}
        style={pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : undefined}
        aria-label={open ? "Close research copilot" : "Open research copilot"}
        aria-expanded={open}
        title="Research copilot (drag to move)"
        onPointerDown={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          drag.current = {
            dx: event.clientX - rect.left,
            dy: event.clientY - rect.top,
            downX: event.clientX,
            downY: event.clientY,
            moved: false,
          };
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          const state = drag.current;
          if (!state) return;
          if (
            !state.moved &&
            Math.hypot(event.clientX - state.downX, event.clientY - state.downY) >
              DRAG_THRESHOLD_PX
          ) {
            state.moved = true;
          }
          if (state.moved) {
            setPos(clamp({ x: event.clientX - state.dx, y: event.clientY - state.dy }));
          }
        }}
        onPointerUp={(event) => {
          const state = drag.current;
          drag.current = null;
          if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
            event.currentTarget.releasePointerCapture?.(event.pointerId);
          }
          if (!state?.moved) return;
          suppressClick.current = true;
          const landed = clamp({ x: event.clientX - state.dx, y: event.clientY - state.dy });
          setPos(landed);
          try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(landed));
          } catch {
            // Private mode: the spot just doesn't persist.
          }
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
        onClick={() => {
          if (suppressClick.current) {
            suppressClick.current = false;
            return;
          }
          setOpen((current) => !current);
        }}
      >
        <RobotFace />
      </button>
      {open ? (
        <div className={styles.overlay} role="dialog" aria-label="Research copilot chat">
          <button
            type="button"
            className={styles.close}
            aria-label="Close copilot chat"
            onClick={() => setOpen(false)}
          >
            ×
          </button>
          <CopilotPanel
            projectId={projectId}
            graph={graph}
            disabled={disabled}
            view={view}
            selection={selection}
            diagramElements={diagramElements}
            onSubmit={onSubmit}
            onSelectDiagram={onSelectDiagram}
          />
        </div>
      ) : null}
    </>
  );
}
