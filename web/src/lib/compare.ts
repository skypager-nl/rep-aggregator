import { useSyncExternalStore } from "react";

// Per-viewer convenience only; survives reloads when storage is available.
const KEY = "repagg.compare";
const MAX = 4;
let ids: string[] = read();
const listeners = new Set<() => void>();

function read(): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function write(next: string[]) {
  ids = next.slice(-MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable: keep in memory */
  }
  listeners.forEach((l) => l());
}

export const compare = {
  toggle: (id: string) => write(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]),
  set: (next: string[]) => write(next),
  clear: () => write([]),
};

export function useCompare(): string[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => ids,
  );
}
