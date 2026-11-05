// Progress store: holds the Progress document in memory, persists every change
// to localStorage synchronously (so closing the tab never loses work), and
// keeps several open tabs in sync via the "storage" event.
import { useSyncExternalStore } from "react";
import { PROGRESS_STORAGE_KEY, emptyProgress, parseProgress, type Progress } from "./progress";

export interface StorageDiagnostics {
  available: boolean;
  bytes: number;
  lastSavedAt: string | null;
  loadWarning: string | null;
  saveError: string | null;
}

function getStorage(): Storage | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    const probe = "groundwork:probe";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return null;
  }
}

export class ProgressStore {
  private state: Progress;
  private listeners = new Set<() => void>();
  private storage: Storage | null;
  private diagnostics: StorageDiagnostics;

  constructor(storage: Storage | null = getStorage()) {
    this.storage = storage;
    this.diagnostics = { available: storage !== null, bytes: 0, lastSavedAt: null, loadWarning: null, saveError: null };
    this.state = this.read();
    if (typeof window !== "undefined") {
      window.addEventListener("storage", (e) => {
        if (e.key !== PROGRESS_STORAGE_KEY || !e.newValue) return;
        try {
          const parsed = parseProgress(JSON.parse(e.newValue));
          if (parsed.ok) {
            this.state = parsed.progress;
            this.emit();
          } else {
            // Another tab (or an extension) may have written data that does not
            // match our schema. Ignore it rather than letting a storage event
            // crash the page or replace a valid in-memory profile.
            this.diagnostics = { ...this.diagnostics, loadWarning: `Ignored an invalid progress update from another tab: ${parsed.error}` };
            this.emit();
          }
        } catch (error) {
          this.diagnostics = {
            ...this.diagnostics,
            loadWarning: `Ignored an unreadable progress update from another tab: ${error instanceof Error ? error.message : String(error)}`,
          };
          this.emit();
        }
      });
    }
  }

  private read(): Progress {
    if (!this.storage) {
      this.diagnostics.loadWarning =
        "Browser storage is unavailable (private mode or blocked). Progress will be lost when you close this tab — export it to keep it.";
      return emptyProgress();
    }
    const raw = this.storage.getItem(PROGRESS_STORAGE_KEY);
    if (!raw) return emptyProgress();
    this.diagnostics.bytes = raw.length * 2;
    try {
      const parsed = parseProgress(JSON.parse(raw));
      if (parsed.ok) return parsed.progress;
      throw new Error(parsed.error);
    } catch (e) {
      const backupKey = `${PROGRESS_STORAGE_KEY}:unreadable:${Date.now()}`;
      try {
        this.storage.setItem(backupKey, raw);
      } catch {
        /* storage full: nothing more we can do */
      }
      this.diagnostics.loadWarning = `Saved progress could not be read (${(e as Error).message}). A copy was kept under "${backupKey}" and a fresh profile was started.`;
      return emptyProgress();
    }
  }

  private persist() {
    if (!this.storage) return;
    try {
      const raw = JSON.stringify(this.state);
      this.storage.setItem(PROGRESS_STORAGE_KEY, raw);
      this.diagnostics = { ...this.diagnostics, bytes: raw.length * 2, lastSavedAt: new Date().toISOString(), saveError: null };
    } catch (e) {
      this.diagnostics = { ...this.diagnostics, saveError: `Could not save progress: ${(e as Error).message}. Export your progress to keep it safe.` };
    }
  }

  private emit() {
    this.listeners.forEach((l) => l());
  }

  get = (): Progress => this.state;
  getDiagnostics = (): StorageDiagnostics => this.diagnostics;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  update(transition: (p: Progress, now: Date) => Progress): void {
    const next = transition(this.state, new Date());
    if (next === this.state) return;
    this.state = next;
    this.persist();
    this.emit();
  }

  replace(progress: Progress): void {
    this.state = progress;
    this.persist();
    this.emit();
  }

  reset(): void {
    const theme = this.state.settings;
    this.state = { ...emptyProgress(), settings: { ...emptyProgress().settings, theme: theme.theme, motion: theme.motion } };
    this.persist();
    this.emit();
  }
}

export const progressStore = new ProgressStore();

export function useProgress(): Progress {
  return useSyncExternalStore(progressStore.subscribe, progressStore.get, progressStore.get);
}

export function useProgressSelector<T>(select: (p: Progress) => T): T {
  return useSyncExternalStore(
    progressStore.subscribe,
    () => select(progressStore.get()),
    () => select(progressStore.get()),
  );
}
