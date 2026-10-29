import { useEffect, useMemo, useRef, useState } from "react";
import { useWorkspaceSelection } from "../../lib/store.ts";
import type {
  GraphLayout,
  GraphNode,
  MeasuredOverlay,
  MethodologyGraph,
} from "../../lib/types.ts";
import { EMPTY_OVERLAY } from "../../lib/types.ts";
import { locatorSummary } from "../workspace/EvidencePanel.tsx";
import type { CanvasDiffStatuses } from "./flowElements.ts";
import { deriveFlowSteps } from "./flowSteps.ts";
import { GraphCanvas } from "./GraphCanvas.tsx";
import styles from "./FlowView.module.css";

const PLAY_INTERVAL_MS = 2600;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function stepEvidence(node: GraphNode): string {
  const first = node.evidence[0];
  return first ? locatorSummary(first) : "no recorded evidence";
}

/** Flow view: an animated step-by-step walkthrough of the method.
 *  Steps follow the graph's layer order; the active step selects
 *  its node, so the inspector and evidence rail explain it. Step
 *  ids are graph node ids — the same model live telemetry will
 *  later drive through the measured overlay. */
export function FlowView({
  graph,
  layout,
  diffStatuses,
  overlay = EMPTY_OVERLAY,
  mutating,
}: {
  graph: MethodologyGraph;
  layout: GraphLayout | null;
  diffStatuses: CanvasDiffStatuses | null;
  overlay?: MeasuredOverlay;
  mutating?: boolean;
}) {
  const steps = useMemo(() => deriveFlowSteps(graph), [graph]);
  const nodes = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const { selectNodes } = useWorkspaceSelection();
  const timer = useRef<number | null>(null);

  const active = steps[Math.min(index, Math.max(steps.length - 1, 0))] ?? null;

  useEffect(() => {
    if (active) selectNodes([active.nodeId]);
  }, [active, selectNodes]);

  useEffect(() => {
    if (!playing || steps.length === 0) return;
    timer.current = window.setInterval(() => {
      setIndex((current) => {
        if (current + 1 >= steps.length) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, PLAY_INTERVAL_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing, steps.length]);

  function togglePlay(): void {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (prefersReducedMotion()) return;
    setIndex((current) => (current + 1 >= steps.length ? 0 : current));
    setPlaying(true);
  }

  if (steps.length === 0) return null;

  return (
    <div className={styles.view}>
      <div className={styles.transport} role="group" aria-label="Walkthrough controls">
        <button
          type="button"
          onClick={() => {
            setPlaying(false);
            setIndex((current) => Math.max(0, current - 1));
          }}
          disabled={index === 0}
        >
          Previous
        </button>
        <button
          type="button"
          onClick={togglePlay}
          title={
            prefersReducedMotion()
              ? "Auto-play disabled by reduced-motion preference"
              : playing
                ? "Pause the walkthrough"
                : "Play the walkthrough"
          }
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={() => {
            setPlaying(false);
            setIndex((current) => Math.min(steps.length - 1, current + 1));
          }}
          disabled={index >= steps.length - 1}
        >
          Next
        </button>
        <span className={styles.position} aria-live="polite">
          Step {(active?.index ?? 0) + 1} of {steps.length}
        </span>
      </div>
      <ol className={styles.steps} aria-label="Method steps">
        {steps.map((step) => {
          const node = nodes.get(step.nodeId);
          if (!node) return null;
          const current = step.nodeId === active?.nodeId;
          return (
            <li key={step.nodeId}>
              <button
                type="button"
                className={current ? styles.current : undefined}
                aria-current={current ? "step" : undefined}
                onClick={() => {
                  setPlaying(false);
                  setIndex(step.index);
                }}
              >
                <span className={styles.stepIndex}>{step.index + 1}</span>
                <span className={styles.stepLabel}>{node.label}</span>
                <span className={styles.stepMeta}>
                  {node.kind} · {stepEvidence(node)}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <GraphCanvas
        key={`flow-walk-${graph.version}`}
        graph={graph}
        layout={layout}
        diffStatuses={diffStatuses}
        overlay={overlay}
        mutating={mutating}
      />
    </div>
  );
}
