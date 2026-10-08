import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

/* Web storage is process-global in jsdom: a test that persists UI state
 * (e.g. the assistant dock remembering it is open) must not leak into the
 * next render. */
afterEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

/* jsdom no implementa scrollIntoView — el checklist de emisión lo usa para
 * llevar al primer campo pendiente. */
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => undefined);
