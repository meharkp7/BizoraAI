/* Revision history for undo/redo: the stack tracks viewed versions, and
   every committed patch clears the redo branch. External navigation (an
   edited URL, browser back/forward) resets the stacks. */

import { useEffect, useRef, useState } from "react";

export interface RevisionHistory {
  canUndo: boolean;
  canRedo: boolean;
  /** Navigate to a version as a new history entry. */
  go: (version: number) => void;
  undo: () => void;
  redo: () => void;
}

export function useRevisionHistory(
  current: number,
  onNavigate: (version: number) => void,
): RevisionHistory {
  const [past, setPast] = useState<number[]>([]);
  const [future, setFuture] = useState<number[]>([]);
  const expecting = useRef<number | null>(null);

  useEffect(() => {
    if (expecting.current === current) {
      expecting.current = null;
    } else {
      // Landed here without going through go/undo/redo: drop stale stacks.
      setPast([]);
      setFuture([]);
    }
  }, [current]);

  function go(version: number): void {
    if (version === current) return;
    setPast((previous) => [...previous, current]);
    setFuture([]);
    expecting.current = version;
    onNavigate(version);
  }

  function undo(): void {
    if (past.length === 0) return;
    const previous = past[past.length - 1];
    setPast(past.slice(0, -1));
    setFuture((next) => [current, ...next]);
    expecting.current = previous;
    onNavigate(previous);
  }

  function redo(): void {
    if (future.length === 0) return;
    const [next, ...rest] = future;
    setPast((previous) => [...previous, current]);
    setFuture(rest);
    expecting.current = next;
    onNavigate(next);
  }

  return { canUndo: past.length > 0, canRedo: future.length > 0, go, undo, redo };
}
