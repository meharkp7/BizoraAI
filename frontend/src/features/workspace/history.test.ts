import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useRevisionHistory } from "./history.ts";

describe("useRevisionHistory", () => {
  it("walks back and forward through viewed versions", () => {
    const onNavigate = vi.fn();
    let current = 1;
    const { result, rerender } = renderHook(
      ({ version }: { version: number }) => useRevisionHistory(version, onNavigate),
      { initialProps: { version: 1 } },
    );

    expect(result.current.canUndo).toBe(false);
    act(() => result.current.go(2));
    expect(onNavigate).toHaveBeenCalledWith(2);
    current = 2;
    rerender({ version: current });
    expect(result.current.canUndo).toBe(true);

    act(() => result.current.undo());
    expect(onNavigate).toHaveBeenCalledWith(1);
    current = 1;
    rerender({ version: current });
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(true);

    act(() => result.current.redo());
    expect(onNavigate).toHaveBeenCalledWith(2);
  });

  it("clears redo on a new navigation and ignores no-ops", () => {
    const onNavigate = vi.fn();
    const { result, rerender } = renderHook(
      ({ version }: { version: number }) => useRevisionHistory(version, onNavigate),
      { initialProps: { version: 2 } },
    );

    act(() => result.current.go(2));
    expect(onNavigate).not.toHaveBeenCalled();
    act(() => result.current.undo());
    expect(onNavigate).not.toHaveBeenCalled();

    act(() => result.current.go(3));
    rerender({ version: 3 });
    act(() => result.current.undo());
    rerender({ version: 2 });
    expect(result.current.canRedo).toBe(true);
    act(() => result.current.go(4));
    rerender({ version: 4 });
    expect(result.current.canRedo).toBe(false);
  });

  it("resets stacks on external navigation", () => {
    const onNavigate = vi.fn();
    const { result, rerender } = renderHook(
      ({ version }: { version: number }) => useRevisionHistory(version, onNavigate),
      { initialProps: { version: 1 } },
    );

    act(() => result.current.go(2));
    rerender({ version: 2 });
    expect(result.current.canUndo).toBe(true);
    // URL edited by hand or browser back/forward: stacks no longer apply.
    rerender({ version: 5 });
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });
});
