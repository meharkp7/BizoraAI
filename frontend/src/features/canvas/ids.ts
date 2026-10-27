/* Collision-free id suggestions for canvas-created nodes and edges. */

export const NODE_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$/;

export function isValidNodeId(id: string): boolean {
  return NODE_ID_PATTERN.test(id);
}

/** Smallest free `node-<n>` id. */
export function suggestNodeId(taken: Set<string>): string {
  let counter = 1;
  while (taken.has(`node-${counter}`)) counter += 1;
  return `node-${counter}`;
}

/** `e-<source>-<target>`, suffixed while taken. Deterministic per graph. */
export function suggestEdgeId(source: string, target: string, taken: Set<string>): string {
  const base = `e-${source}-${target}`.slice(0, 100);
  if (!taken.has(base)) return base;
  let counter = 2;
  while (taken.has(`${base}-${counter}`)) counter += 1;
  return `${base}-${counter}`;
}
