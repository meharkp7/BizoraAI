import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server.ts";

// React Flow requires ResizeObserver, which jsdom does not implement. The
// stub reports a fixed rect per observed element so measured rendering
// (node initialization, edge paths) settles deterministically.
class ResizeObserverStub {
  private callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element): void {
    const callback = this.callback;
    const self = this as unknown as ResizeObserver;
    const rect = {
      x: 0,
      y: 0,
      width: 120,
      height: 60,
      top: 0,
      left: 0,
      right: 120,
      bottom: 60,
      toJSON: () => ({}),
    };
    const entry = {
      target,
      contentRect: rect,
      borderBoxSize: [],
      contentBoxSize: [],
      devicePixelContentBoxSize: [],
    } as unknown as ResizeObserverEntry;
    queueMicrotask(() => callback([entry], self));
  }

  unobserve(): void {}

  disconnect(): void {}
}
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = ResizeObserverStub;
}

// React Flow reads viewport transforms through DOMMatrix, which jsdom does
// not implement. Identity-only behavior is enough for unit tests.
class DOMMatrixStub {
  a = 1;
  b = 0;
  c = 0;
  d = 1;
  e = 0;
  f = 0;

  translate(): this {
    return this;
  }

  scale(): this {
    return this;
  }

  multiply(): this {
    return this;
  }

  inverse(): this {
    return this;
  }

  transformPoint(point?: { x: number; y: number }): { x: number; y: number } {
    return { x: point?.x ?? 0, y: point?.y ?? 0 };
  }
}
if (typeof window !== "undefined") {
  if (!window.DOMMatrixReadOnly) {
    window.DOMMatrixReadOnly = DOMMatrixStub as unknown as typeof DOMMatrixReadOnly;
  }
  if (!window.DOMMatrix) {
    window.DOMMatrix = DOMMatrixStub as unknown as typeof DOMMatrix;
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
