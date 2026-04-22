import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Node 25+ ships a native `localStorage` that is activated by a runtime flag
// and exposes only a partial API without `clear()`. When vitest runs under
// jsdom it normally provides a full Storage implementation on window, but the
// native stub can shadow it depending on flag state. Install our own in-memory
// Storage polyfill to guarantee identical behavior on Node 20 (CI) and Node
// 25+ (local dev). See master plan §14 for context.
class MemoryStorage {
  constructor() {
    this._data = new Map();
  }
  get length() {
    return this._data.size;
  }
  key(i) {
    return Array.from(this._data.keys())[i] ?? null;
  }
  getItem(k) {
    return this._data.has(k) ? this._data.get(k) : null;
  }
  setItem(k, v) {
    this._data.set(String(k), String(v));
  }
  removeItem(k) {
    this._data.delete(k);
  }
  clear() {
    this._data.clear();
  }
}

const polyfill = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  value: polyfill,
  writable: true,
  configurable: true,
});
if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    value: polyfill,
    writable: true,
    configurable: true,
  });
}

afterEach(() => {
  cleanup();
});
