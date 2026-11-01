import { useEffect, useMemo, useRef, useState } from "react";
import type { CircuitIRJson } from "../../lib/types.ts";
import styles from "./SignalFlow.module.css";
import { deriveCircuitSteps, sharedNet } from "./flowOrder.ts";
import type { DiagramSelection } from "./selection.ts";
import { schematicSelection } from "./selection.ts";
import { pickSvgId } from "./svgPick.ts";
import type { DeviceSpan, WirePoint } from "./wireRoute.ts";
import {
  pointAtLength,
  polylineLength,
  routeAlongWires,
} from "./wireRoute.ts";
import diagramStyles from "./DiagramView.module.css";

const PLAY_INTERVAL_MS = 2600;
const PULSE_SPEED_PX_S = 300;
const HOP_FADE_MS = 140;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

interface SvgTransform {
  vbX: number;
  vbY: number;
  scale: number;
  offX: number;
  offY: number;
}

/** Map between SVG units and canvas pixels for the rendered schematic. */
function readTransform(canvas: HTMLElement): SvgTransform | null {
  const svg = canvas.querySelector("svg");
  const parts = (svg?.getAttribute("viewBox") ?? "").split(/[\s,]+/).map(Number);
  if (
    !svg ||
    parts.length !== 4 ||
    parts.some((n) => !Number.isFinite(n)) ||
    parts[2] <= 0
  ) {
    return null;
  }
  const rect = svg.getBoundingClientRect();
  const host = canvas.getBoundingClientRect();
  if (!(rect.width > 0)) return null;
  return {
    vbX: parts[0],
    vbY: parts[1],
    scale: rect.width / parts[2],
    offX: rect.left - host.left,
    offY: rect.top - host.top,
  };
}

function centerOf(canvas: HTMLElement, id: string): WirePoint | null {
  const group = canvas.querySelector(`[data-id="${id}"]`);
  if (!group) return null;
  const rect = (group as SVGGraphicsElement).getBoundingClientRect();
  const host = canvas.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return {
    x: rect.left - host.left + rect.width / 2,
    y: rect.top - host.top + rect.height / 2,
  };
}

/** Device bodies in SVG units, so the router can bridge the copper
 *  islands the symbols cut the wires into (see wireRoute). */
function spansOf(canvas: HTMLElement, transform: SvgTransform): DeviceSpan[] {
  const host = canvas.getBoundingClientRect();
  const spans: DeviceSpan[] = [];
  for (const group of canvas.querySelectorAll("[data-id]")) {
    const rect = (group as SVGGElement).getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;
    spans.push({
      x: transform.vbX + (rect.left - host.left - transform.offX) / transform.scale,
      y: transform.vbY + (rect.top - host.top - transform.offY) / transform.scale,
      w: rect.width / transform.scale,
      h: rect.height / transform.scale,
    });
  }
  return spans;
}

/** Schematic signal-flow walkthrough: Previous/Play/Next steps through
 *  the circuit in connectivity order (see flowOrder.ts), a pulse dot
 *  travels point to point, and each step opens its component in the
 *  Inspector with the paper evidence behind it. */
export function SignalFlow({
  circuit,
  svg,
  netLabels,
  onSelect,
}: {
  circuit: CircuitIRJson;
  svg: string;
  netLabels: ReadonlyMap<string, string>;
  onSelect: (selection: DiagramSelection) => void;
}) {
  const steps = useMemo(() => deriveCircuitSteps(circuit), [circuit]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pulse, setPulse] = useState<WirePoint | null>(null);
  const [dimmed, setDimmed] = useState(false);
  // Where the dot sat before this step: a click-jump lands several
  // steps away, so the tag's origin is the previous step, not the
  // previous index. Updated only in the step handlers below.
  const [prevId, setPrevId] = useState<string | null>(null);
  const indexRef = useRef(0);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | null>(null);
  const hopTimers = useRef<number[]>([]);
  // Live pulse position (canvas pixels): flights start from here, so an
  // interrupted flight resumes mid-wire instead of jumping backwards.
  const pulseRef = useRef<WirePoint | null>(null);
  const flight = useRef<number | null>(null);

  function place(point: WirePoint | null): void {
    pulseRef.current = point;
    setPulse(point);
  }

  // The parent keys this component by figure, so picking another
  // circuit remounts it and the walkthrough restarts from step 1.
  const activeId = steps[Math.min(index, Math.max(steps.length - 1, 0))] ?? null;
  const active = circuit.components.find((entry) => entry.id === activeId) ?? null;
  const prev = prevId
    ? (circuit.components.find((entry) => entry.id === prevId) ?? null)
    : null;
  const viaNet =
    prevId && activeId ? sharedNet(circuit, prevId, activeId) : null;
  const tagLeg =
    prev && active ? `${prev.label} → ${active.label}` : "Flow starts here";
  const tagVia = !prev
    ? null
    : viaNet
      ? `via ${netLabels.get(viaNet) ?? viaNet}`
      : "Separate branch";
  // What this stop does, in the paper's own words: the component's
  // evidence quote, or nothing when the paper says nothing about it.
  const rawImpact = active?.evidence?.quote?.replace(/\s+/g, " ").trim() ?? "";
  const impact =
    rawImpact.length > 110
      ? `${rawImpact.slice(0, 109).trimEnd()}…`
      : rawImpact || null;

  // Each step opens its component in the Inspector, like the old flow
  // view selected its node: the rail always explains the pulse.
  useEffect(() => {
    if (active) onSelect(schematicSelection(active, netLabels));
  }, [active, netLabels, onSelect]);

  useEffect(() => {
    if (!playing || steps.length === 0) return;
    timer.current = window.setInterval(() => {
      const current = indexRef.current;
      if (current + 1 >= steps.length) {
        setPlaying(false);
        return;
      }
      indexRef.current = current + 1;
      setPrevId(steps[current] ?? null);
      setIndex(current + 1);
    }, PLAY_INTERVAL_MS);
    return () => {
      if (timer.current !== null) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing, steps]);

  // Highlight ring follows the active group across re-renders.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    for (const group of canvas.querySelectorAll("[data-id]")) {
      group.classList.toggle("flow-active", group.getAttribute("data-id") === activeId);
    }
  }, [activeId, svg]);

  // Pulse dot tracks the active group's centre.
  // The pulse flies along the drawn wires from the previous step to
  // the new one at constant speed; disconnected copper fades out here
  // and back in there instead of drawing a wire that does not exist.
  // Reduced motion lands straight on the target. Scroll needs no
  // handling: the pulse sits inside the scrolling content, so
  // relative math is stable.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const cancel = (): void => {
      if (flight.current !== null) {
        cancelAnimationFrame(flight.current);
        flight.current = null;
      }
    };
    const clearHops = (): void => {
      hopTimers.current.forEach((id) => window.clearTimeout(id));
      hopTimers.current = [];
    };
    const target = activeId ? centerOf(canvas, activeId) : null;
    if (!target) {
      cancel();
      clearHops();
      setDimmed(false);
      place(null);
      return;
    }
    const from = pulseRef.current;
    const transform = readTransform(canvas);
    const d = canvas.querySelector("path.wire")?.getAttribute("d") ?? "";
    const settled =
      !from || Math.hypot(from.x - target.x, from.y - target.y) < 2;
    let path: WirePoint[] | null = null;
    if (!settled && transform && d && !prefersReducedMotion() && from) {
      const toSvg = (p: WirePoint): WirePoint => ({
        x: transform.vbX + (p.x - transform.offX) / transform.scale,
        y: transform.vbY + (p.y - transform.offY) / transform.scale,
      });
      const route = routeAlongWires(
        d,
        toSvg(from),
        toSvg(target),
        spansOf(canvas, transform),
      );
      if (route && route.length >= 2) {
        path = route.map((p) => ({
          x: transform.offX + (p.x - transform.vbX) * transform.scale,
          y: transform.offY + (p.y - transform.vbY) * transform.scale,
        }));
      }
    }
    cancel();
    clearHops();
    if (!path) {
      if (from && !settled && !prefersReducedMotion()) {
        setDimmed(true);
        hopTimers.current.push(
          window.setTimeout(() => {
            place(target);
            setDimmed(false);
          }, HOP_FADE_MS),
        );
      } else {
        setDimmed(false);
        place(target);
      }
    } else {
      setDimmed(false);
      const flightPath = path;
      const total = polylineLength(flightPath);
      const duration = Math.max(
        180,
        Math.min(1100, (total / PULSE_SPEED_PX_S) * 1000),
      );
      const started = performance.now();
      const tick = (now: number): void => {
        const k = Math.min(1, (now - started) / duration);
        place(pointAtLength(flightPath, k * total));
        flight.current = k < 1 ? requestAnimationFrame(tick) : null;
      };
      flight.current = requestAnimationFrame(tick);
    }
    // A resize invalidates the flight geometry: land outright. The
    // observer always fires once on observe, so skip that first call.
    let primed = false;
    const observer =
      typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
            if (!primed) {
              primed = true;
              return;
            }
            cancel();
            clearHops();
            setDimmed(false);
            if (activeId) place(centerOf(canvas, activeId));
          })
        : null;
    observer?.observe(canvas);
    return () => {
      cancel();
      clearHops();
      observer?.disconnect();
    };
    // place touches refs and state only; the step and the artwork retrigger.
  }, [activeId, svg]);

  function togglePlay(): void {
    if (playing) {
      setPlaying(false);
      return;
    }
    if (prefersReducedMotion()) return;
    if (indexRef.current + 1 >= steps.length) {
      setPrevId(steps[indexRef.current] ?? null);
      indexRef.current = 0;
      setIndex(0);
    }
    setPlaying(true);
  }

  function stepTo(next: number): void {
    setPlaying(false);
    const clamped = Math.max(0, Math.min(next, steps.length - 1));
    if (clamped !== indexRef.current) {
      setPrevId(steps[indexRef.current] ?? null);
      indexRef.current = clamped;
    }
    setIndex(clamped);
  }

  return (
    <div className={styles.flow}>
      <div className={styles.transport} role="group" aria-label="Signal flow walkthrough">
        <button type="button" onClick={() => stepTo(index - 1)} disabled={index === 0}>
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
          onClick={() => stepTo(index + 1)}
          disabled={index + 1 >= steps.length}
        >
          Next
        </button>
        <p className={styles.caption} aria-live="polite">
          {active
            ? `Step ${index + 1} of ${steps.length} — ${active.label} (${active.type})`
            : "No steps"}
        </p>
      </div>
      <div
        ref={canvasRef}
        className={`${diagramStyles.canvas} ${styles.stage}`}
        role="group"
        aria-label="Schematic diagram"
        onClick={(event) => {
          const id = pickSvgId(
            event.currentTarget,
            event.target as Element | null,
            { x: event.clientX, y: event.clientY },
            "data-id",
          );
          if (!id) return;
          const component = circuit.components.find((entry) => entry.id === id);
          if (!component) return;
          const stepIndex = steps.indexOf(id);
          if (stepIndex !== -1) stepTo(stepIndex);
          else onSelect(schematicSelection(component, netLabels));
        }}
      >
        <div dangerouslySetInnerHTML={{ __html: svg }} className={styles.svg} />
        {pulse ? (
          <div
            className={`${styles.pulse}${dimmed ? ` ${styles.dimmed}` : ""}`}
            style={{ left: pulse.x, top: pulse.y }}
            aria-hidden="true"
            data-testid="flow-pulse"
          />
        ) : null}
        {pulse && active ? (
          <div
            className={`${styles.tag}${dimmed ? ` ${styles.dimmed}` : ""}`}
            style={{ left: pulse.x, top: pulse.y }}
            aria-hidden="true"
            data-testid="flow-tag"
          >
            <span className={styles.tagStep}>
              {`Step ${index + 1} of ${steps.length} — ${active.label}`}
            </span>
            <span className={styles.tagLeg}>{tagLeg}</span>
            {tagVia ? <span className={styles.tagVia}>{tagVia}</span> : null}
            {impact ? <span className={styles.tagWhy}>{impact}</span> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
