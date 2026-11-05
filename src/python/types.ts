// Shapes returned by python/gw_runner.py (kept in sync by tests/python-runner.test.ts).

export interface PyError {
  type: string;
  message: string;
  line: number | null;
  column: number | null;
  traceback: string;
}

export interface InputEvent {
  kind: "input";
  /** Character offset in stdout where the value was consumed. */
  at: number;
  value: string;
}

/** How the host finished a request. "timeout" and "unavailable" are produced by the JS host, not Python. */
export type RunStatus = "completed" | "timeout" | "unavailable";

export interface RunResult {
  status: RunStatus;
  ok: boolean;
  stdout: string;
  stderr: string;
  events: InputEvent[];
  error: PyError | null;
  exitCode: number | string | null;
  durationMs: number;
  /** Human-readable reason when status is not "completed". */
  hostMessage?: string;
}

export type HeapKind = "primitive" | "list" | "tuple" | "set" | "dict" | "function" | "class" | "module" | "instance" | "other";

export interface HeapObject {
  type: string;
  kind: HeapKind;
  repr: string;
  items?: number[];
  entries?: [number, number][];
  attrs?: [string, number][];
  size?: number;
}

export interface TraceFrame {
  name: string;
  line: number;
  vars: { name: string; ref: number }[];
}

export interface TraceStep {
  /** "yield" = a generator/coroutine pausing (its frame survives); "return" = a frame finishing. */
  event: "call" | "line" | "return" | "yield" | "exception";
  line: number;
  stack: TraceFrame[];
  heap: Record<string, HeapObject>;
  stdoutLength: number;
  returnRef?: number;
  exception?: { type: string; message: string };
}

export interface TraceResult extends RunResult {
  steps: TraceStep[];
  truncated: boolean;
}

export interface ExerciseTest {
  name: string;
  code: string;
}

export interface TestOutcome {
  name: string;
  passed: boolean;
  message: string;
  printed: string;
}

export interface GradeResult {
  run: RunResult;
  tests: TestOutcome[];
  passed: boolean;
}

export interface RunOptions {
  stdin?: string;
  /** Wall-clock limit in milliseconds (browser host only). */
  timeoutMs?: number;
}
