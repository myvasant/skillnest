import { describe, expect, it } from "vitest";
import { HISTORY_LIMIT, PROGRESS_STORAGE_KEY, createExport, emptyProgress, parseExport, parseProgress } from "../../src/storage/progress";
import { ProgressStore } from "../../src/storage/store";
import { recordAttempt, saveCode, saveSnippet, setMilestone, rateInterviewQuestion } from "../../src/storage/actions";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();
  failWrites = false;
  get length() {
    return this.data.size;
  }
  clear() {
    this.data.clear();
  }
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  key(i: number) {
    return [...this.data.keys()][i] ?? null;
  }
  removeItem(k: string) {
    this.data.delete(k);
  }
  setItem(k: string, v: string) {
    if (this.failWrites) throw new Error("QuotaExceededError");
    this.data.set(k, v);
  }
}

const T0 = new Date("2026-10-22T10:00:00Z");

describe("progress schema", () => {
  it("round-trips through export and import", () => {
    let p = emptyProgress(T0);
    p = recordAttempt(p, { gid: "l/q", correct: true, context: "practice" }, T0);
    p = saveSnippet(p, { id: "s1", title: "Mine", code: "print(1)" }, T0);
    p = setMilestone(p, "calc", "m1", true, "tests", T0);
    p = rateInterviewQuestion(p, "q", "solid", T0);
    const file = JSON.stringify(createExport(p, "0.1.0", T0));
    const back = parseExport(file);
    expect(back.ok).toBe(true);
    if (back.ok) expect(back.progress).toEqual(p);
  });

  it("rejects non-JSON, foreign files, and corrupt progress with a clear message", () => {
    expect(parseExport("not json")).toMatchObject({ ok: false, error: expect.stringMatching(/not valid JSON/) });
    expect(parseExport(JSON.stringify({ hello: 1 }))).toMatchObject({ ok: false, error: expect.stringMatching(/not a Groundwork/) });
    const bad = createExport(emptyProgress(T0), "0.1.0") as unknown as { progress: Record<string, unknown> };
    bad.progress.items = { x: { attempts: "many" } };
    expect(parseExport(JSON.stringify(bad))).toMatchObject({ ok: false, error: expect.stringMatching(/items\.x\.attempts/) });
  });

  it("refuses data from a newer schema version", () => {
    const future = { ...emptyProgress(T0), schemaVersion: 99 };
    expect(parseProgress(future)).toMatchObject({ ok: false, error: expect.stringMatching(/newer version/) });
  });

  it("fills defaults for missing optional sections", () => {
    const minimal = { schemaVersion: 1, createdAt: T0.toISOString(), updatedAt: T0.toISOString() };
    const r = parseProgress(minimal);
    expect(r.ok && r.progress.settings.theme).toBe("system");
  });

  it("caps history length", () => {
    let p = emptyProgress(T0);
    for (let i = 0; i < HISTORY_LIMIT + 25; i++) p = recordAttempt(p, { gid: `g${i % 7}`, correct: i % 2 === 0, context: "practice" }, T0);
    expect(p.history.length).toBe(HISTORY_LIMIT);
    expect(p.items.g0!.attempts).toBeGreaterThan(0);
  });

  it("returns the same object when nothing changes (avoids needless writes)", () => {
    const p = saveCode(emptyProgress(T0), "k", "x", T0);
    expect(saveCode(p, "k", "x", T0)).toBe(p);
  });
});

describe("ProgressStore persistence", () => {
  it("persists updates and reloads them in a new store (close and reopen)", () => {
    const storage = new MemoryStorage();
    const a = new ProgressStore(storage);
    a.update((p, now) => recordAttempt(p, { gid: "l/q", correct: true, context: "practice" }, now));
    const b = new ProgressStore(storage);
    expect(b.get().items["l/q"]?.correct).toBe(1);
  });

  it("keeps a backup and starts fresh when stored data is unreadable", () => {
    const storage = new MemoryStorage();
    storage.setItem(PROGRESS_STORAGE_KEY, "{broken");
    const store = new ProgressStore(storage);
    expect(store.get().schemaVersion).toBe(1);
    expect(store.getDiagnostics().loadWarning).toMatch(/could not be read/);
    expect([...Array(storage.length).keys()].map((i) => storage.key(i)).some((k) => k?.includes(":unreadable:"))).toBe(true);
  });

  it("reports save failures instead of crashing", () => {
    const storage = new MemoryStorage();
    const store = new ProgressStore(storage);
    storage.failWrites = true;
    store.update((p, now) => saveCode(p, "k", "x", now));
    expect(store.get().code.k?.code).toBe("x");
    expect(store.getDiagnostics().saveError).toMatch(/Could not save/);
  });

  it("works without storage at all (private mode) and says so", () => {
    const store = new ProgressStore(null);
    store.update((p, now) => saveCode(p, "k", "x", now));
    expect(store.get().code.k?.code).toBe("x");
    expect(store.getDiagnostics().loadWarning).toMatch(/unavailable/);
  });

  it("reset keeps theme preferences", () => {
    const store = new ProgressStore(new MemoryStorage());
    store.update((p, now) => ({ ...saveCode(p, "k", "x", now), settings: { ...p.settings, theme: "dark" } }));
    store.reset();
    expect(store.get().code).toEqual({});
    expect(store.get().settings.theme).toBe("dark");
  });

  it("ignores malformed cross-tab storage events without crashing", () => {
    const previousWindow = globalThis.window;
    let onStorage: ((event: StorageEvent) => void) | undefined;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { addEventListener: (_type: string, listener: (event: StorageEvent) => void) => { onStorage = listener; } },
    });
    try {
      const store = new ProgressStore(new MemoryStorage());
      expect(() => onStorage?.({ key: PROGRESS_STORAGE_KEY, newValue: "{broken" } as StorageEvent)).not.toThrow();
      expect(store.getDiagnostics().loadWarning).toMatch(/unreadable progress update/);
      expect(store.get().schemaVersion).toBe(1);
    } finally {
      if (previousWindow === undefined) Reflect.deleteProperty(globalThis, "window");
      else Object.defineProperty(globalThis, "window", { configurable: true, value: previousWindow });
    }
  });
});
