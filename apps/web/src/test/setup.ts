import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

if (typeof window !== "undefined") {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = window.ResizeObserver || (ResizeObserverMock as any);
  global.ResizeObserver = global.ResizeObserver || (ResizeObserverMock as any);
}

afterEach(cleanup);

