/* Picking inside engine-rendered SVG. Direct hits resolve through the
   engine's data-id/data-node-id groups; near misses (schematic labels
   render beside their symbol, not inside it) fall back to the nearest
   group within a small screen-space radius. */

const NEAR_MISS_PX = 24;

function rectDistance(
  rect: { left: number; top: number; width: number; height: number },
  x: number,
  y: number,
): number {
  const dx = Math.max(rect.left - x, 0, x - (rect.left + rect.width));
  const dy = Math.max(rect.top - y, 0, y - (rect.top + rect.height));
  return Math.hypot(dx, dy);
}

/** Resolve a click to an engine group id, or null when the click is on
 *  empty canvas. `container` is the div hosting the SVG. */
export function pickSvgId(
  container: HTMLElement,
  target: Element | null,
  point: { x: number; y: number },
  attr: "data-id" | "data-node-id",
): string | null {
  const direct = target?.closest?.(`[${attr}]`) ?? null;
  const directId = direct?.getAttribute(attr);
  if (directId) return directId;
  // Labels and wires sit outside the groups: accept the nearest group
  // within a small radius instead of dropping the click.
  let best: string | null = null;
  let bestDist = NEAR_MISS_PX;
  for (const group of container.querySelectorAll(`[${attr}]`)) {
    const rect = (group as SVGGraphicsElement).getBoundingClientRect?.();
    if (!rect || (rect.width === 0 && rect.height === 0)) continue;
    const dist = rectDistance(rect, point.x, point.y);
    if (dist < bestDist) {
      bestDist = dist;
      best = group.getAttribute(attr);
    }
  }
  return best;
}
