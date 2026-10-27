import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useTheme, useWorkspaceSelection } from "./store.ts";

describe("theme store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.dataset.theme = "light";
    useTheme.setState({ theme: "light" });
  });

  it("toggles the theme and persists it", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("bizora-theme")).toBe("dark");
  });
});

describe("workspace selection store", () => {
  beforeEach(() => {
    useWorkspaceSelection.setState({ selectedNodeIds: [], selectedEdgeIds: [] });
  });

  it("selects nodes and clears edge selection", () => {
    const { result } = renderHook(() => useWorkspaceSelection());
    act(() => result.current.selectEdges(["e1"]));
    act(() => result.current.selectNodes(["input"]));
    expect(result.current.selectedNodeIds).toEqual(["input"]);
    expect(result.current.selectedEdgeIds).toEqual([]);
  });

  it("clears all selection", () => {
    const { result } = renderHook(() => useWorkspaceSelection());
    act(() => result.current.selectNodes(["input"]));
    act(() => result.current.clearSelection());
    expect(result.current.selectedNodeIds).toEqual([]);
    expect(result.current.selectedEdgeIds).toEqual([]);
  });
});
