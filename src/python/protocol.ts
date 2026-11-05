import type { ExerciseTest, GradeResult, RunResult, TraceResult } from "./types";

export type WorkerRequest =
  | { id: number; type: "init" }
  | { id: number; type: "run"; code: string; stdin: string }
  | { id: number; type: "trace"; code: string; stdin: string; maxSteps: number }
  | { id: number; type: "grade"; code: string; tests: ExerciseTest[]; stdin: string }
  | { id: number; type: "load-packages"; packages: string[] };

export type WorkerResponse =
  | { id: number; type: "ready"; version: string }
  | { id: number; type: "run"; result: RunResult }
  | { id: number; type: "trace"; result: TraceResult }
  | { id: number; type: "grade"; result: GradeResult }
  | { id: number; type: "packages"; messages: string[] }
  | { id: number; type: "error"; message: string };
