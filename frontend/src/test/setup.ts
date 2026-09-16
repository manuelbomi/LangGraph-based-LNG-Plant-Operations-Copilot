import "@testing-library/jest-dom/vitest";

// @xyflow/react observes element size via ResizeObserver, which jsdom does
// not implement. A minimal no-op stub is enough for it to render in tests.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// recharts' ResponsiveContainer measures its parent via getBoundingClientRect,
// which jsdom reports as all-zero -- recharts then renders nothing. Give it a
// plausible width/height in tests so charts actually render their children.
if (typeof Element !== "undefined") {
  Object.defineProperty(Element.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      width: 800,
      height: 400,
      top: 0,
      left: 0,
      bottom: 400,
      right: 800,
      x: 0,
      y: 0,
      toJSON() {
        return this;
      },
    }),
  });
}
