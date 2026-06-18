/** Vitest global setup: jest-dom matchers + jsdom polyfills. */

import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer needs a non-zero size in jsdom; stub the
// observer so charts render without throwing during component tests.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = globalThis.ResizeObserver ?? ResizeObserverStub;
