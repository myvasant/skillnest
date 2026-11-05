// Glue between a loaded Pyodide instance and python/gw_runner.py.
// Used by the browser worker and by the Node-based content verification tests.
import type { PyodideAPI } from "pyodide";
import type { ExerciseTest, GradeResult, RunResult, TraceResult } from "./types";

const RUNNER_DIR = "/home/pyodide/groundwork";

export function installRunner(py: PyodideAPI, runnerSource: string): void {
  py.FS.mkdirTree(RUNNER_DIR);
  py.FS.writeFile(`${RUNNER_DIR}/gw_runner.py`, runnerSource);
  py.runPython(
    ["import sys", `if ${JSON.stringify(RUNNER_DIR)} not in sys.path: sys.path.insert(0, ${JSON.stringify(RUNNER_DIR)})`, "import gw_runner"].join("\n"),
  );
}

type RunnerFn = "run_json" | "trace_json" | "grade_json";

function callRunner(py: PyodideAPI, fn: RunnerFn, args: unknown[]): unknown {
  const runner = py.pyimport("gw_runner");
  const func = runner[fn];
  try {
    const raw: string = func(...args);
    return JSON.parse(raw);
  } finally {
    func.destroy();
    runner.destroy();
  }
}

type PyRun = Omit<RunResult, "status">;

export function runCode(py: PyodideAPI, code: string, stdin = ""): RunResult {
  return { status: "completed", ...(callRunner(py, "run_json", [code, stdin]) as PyRun) };
}

export function traceCode(py: PyodideAPI, code: string, stdin = "", maxSteps = 400): TraceResult {
  return { status: "completed", ...(callRunner(py, "trace_json", [code, stdin, maxSteps]) as Omit<TraceResult, "status">) };
}

export function gradeCode(py: PyodideAPI, code: string, tests: ExerciseTest[], stdin = ""): GradeResult {
  const raw = callRunner(py, "grade_json", [code, JSON.stringify(tests), stdin]) as {
    run: PyRun;
    tests: GradeResult["tests"];
    passed: boolean;
  };
  return { run: { status: "completed", ...raw.run }, tests: raw.tests, passed: raw.passed };
}
