// Main-thread client for the Pyodide worker.
// - Starts the worker lazily and serialises requests (Python is single-threaded).
// - Enforces a wall-clock limit per request by terminating the worker, which
//   is the only reliable way to stop an infinite loop in WebAssembly.
// - Exposes a status store for UI indicators.
import type { WorkerRequest, WorkerResponse } from "./protocol";
import type { ExerciseTest, GradeResult, RunResult, TraceResult } from "./types";

export type RuntimeStatus = "idle" | "loading" | "ready" | "busy" | "error";

export const DEFAULT_TIMEOUT_MS = 8_000;
const BOOT_TIMEOUT_MS = 60_000;

type Pending = { resolve: (r: WorkerResponse) => void; reject: (e: Error) => void };

type RequestBody = WorkerRequest extends infer R ? (R extends { id: number } ? Omit<R, "id"> : never) : never;

class TimeoutError extends Error {}

function unavailable(message: string): RunResult {
  return { status: "unavailable", ok: false, stdout: "", stderr: "", events: [], error: null, exitCode: null, durationMs: 0, hostMessage: message };
}

function timedOut(limitMs: number): RunResult {
  return {
    status: "timeout",
    ok: false,
    stdout: "",
    stderr: "",
    events: [],
    error: null,
    exitCode: null,
    durationMs: limitMs,
    hostMessage: `Stopped after ${limitMs / 1000} seconds. The Python runtime was restarted.`,
  };
}

export class PythonRuntime {
  private worker: Worker | null = null;
  private booted: Promise<void> | null = null;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private queue: Promise<unknown> = Promise.resolve();
  private status: RuntimeStatus = "idle";
  private lastError: string | null = null;
  private listeners = new Set<() => void>();
  version: string | null = null;

  getStatus = (): RuntimeStatus => this.status;
  getLastError = (): string | null => this.lastError;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private setStatus(status: RuntimeStatus) {
    this.status = status;
    this.listeners.forEach((l) => l());
  }

  private spawn(): Worker {
    const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module", name: "groundwork-python" });
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const p = this.pending.get(event.data.id);
      if (p) {
        this.pending.delete(event.data.id);
        p.resolve(event.data);
      }
    };
    worker.onerror = (event) => {
      const message = event.message || "The Python worker failed to start.";
      this.lastError = message;
      for (const p of this.pending.values()) p.reject(new Error(message));
      this.pending.clear();
    };
    return worker;
  }

  private send(body: RequestBody, timeoutMs: number): Promise<WorkerResponse> {
    const worker = this.worker!;
    const id = this.nextId++;
    return new Promise<WorkerResponse>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new TimeoutError(`timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (r) => {
          clearTimeout(timer);
          resolve(r);
        },
        reject: (e) => {
          clearTimeout(timer);
          reject(e);
        },
      });
      worker.postMessage({ ...body, id } as WorkerRequest);
    });
  }

  /** Start the runtime (download + initialise Pyodide). Safe to call repeatedly. */
  preload(): Promise<void> {
    if (typeof Worker === "undefined") return Promise.reject(new Error("Web Workers are not supported in this browser."));
    if (!this.booted) {
      this.setStatus("loading");
      this.worker = this.spawn();
      this.booted = this.send({ type: "init" }, BOOT_TIMEOUT_MS)
        .then((r) => {
          if (r.type === "error") throw new Error(r.message);
          if (r.type === "ready") this.version = r.version;
          this.lastError = null;
          this.setStatus("ready");
        })
        .catch((e: Error) => {
          this.lastError = e.message;
          this.terminate();
          this.setStatus("error");
          throw e;
        });
    }
    return this.booted;
  }

  private terminate() {
    this.worker?.terminate();
    this.worker = null;
    this.booted = null;
    for (const p of this.pending.values()) p.reject(new Error("runtime restarted"));
    this.pending.clear();
  }

  /** Throw away the interpreter (all state) and start a fresh one. */
  restart(): Promise<void> {
    this.terminate();
    this.setStatus("idle");
    return this.preload();
  }

  private enqueue<T>(task: () => Promise<T>): Promise<T> {
    const run = this.queue.then(task, task);
    this.queue = run.catch(() => undefined);
    return run;
  }

  private async request<T>(
    body: RequestBody,
    timeoutMs: number,
    onTimeout: () => T,
    onUnavailable: (msg: string) => T,
    pick: (r: WorkerResponse) => T | null,
  ): Promise<T> {
    return this.enqueue(async () => {
      try {
        await this.preload();
      } catch (e) {
        return onUnavailable(`The Python runtime could not start: ${(e as Error).message}`);
      }
      this.setStatus("busy");
      try {
        const response = await this.send(body, timeoutMs);
        this.setStatus("ready");
        if (response.type === "error") return onUnavailable(`Runtime error: ${response.message}`);
        return pick(response) ?? onUnavailable("Unexpected response from the Python runtime.");
      } catch (e) {
        if (e instanceof TimeoutError) {
          this.terminate();
          this.setStatus("idle");
          void this.preload().catch(() => undefined);
          return onTimeout();
        }
        this.setStatus(this.worker ? "ready" : "error");
        return onUnavailable((e as Error).message);
      }
    });
  }

  run(code: string, opts: { stdin?: string; timeoutMs?: number } = {}): Promise<RunResult> {
    const limit = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    return this.request<RunResult>(
      { type: "run", code, stdin: opts.stdin ?? "" },
      limit,
      () => timedOut(limit),
      unavailable,
      (r) => (r.type === "run" ? r.result : null),
    );
  }

  trace(code: string, opts: { stdin?: string; maxSteps?: number; timeoutMs?: number } = {}): Promise<TraceResult> {
    const limit = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS * 2;
    return this.request<TraceResult>(
      { type: "trace", code, stdin: opts.stdin ?? "", maxSteps: opts.maxSteps ?? 300 },
      limit,
      () => ({ ...timedOut(limit), steps: [], truncated: true }),
      (msg) => ({ ...unavailable(msg), steps: [], truncated: false }),
      (r) => (r.type === "trace" ? r.result : null),
    );
  }

  grade(code: string, tests: ExerciseTest[], opts: { stdin?: string; timeoutMs?: number } = {}): Promise<GradeResult> {
    const limit = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    return this.request<GradeResult>(
      { type: "grade", code, tests, stdin: opts.stdin ?? "" },
      limit,
      () => ({ run: timedOut(limit), tests: [], passed: false }),
      (msg) => ({ run: unavailable(msg), tests: [], passed: false }),
      (r) => (r.type === "grade" ? r.result : null),
    );
  }

  loadPackages(packages: string[]): Promise<{ ok: boolean; message: string }> {
    return this.request<{ ok: boolean; message: string }>(
      { type: "load-packages", packages },
      120_000,
      () => ({ ok: false, message: "Loading packages timed out. Check your internet connection." }),
      (msg) => ({ ok: false, message: msg }),
      (r) => (r.type === "packages" ? { ok: true, message: r.messages.join("\n") } : null),
    );
  }
}

export const python = new PythonRuntime();
