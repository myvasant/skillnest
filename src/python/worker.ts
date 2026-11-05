/// <reference lib="webworker" />
// Web Worker that hosts Pyodide. Learner code runs here, off the UI thread and
// without access to the page DOM or localStorage. The main thread enforces
// time limits by terminating this worker (see client.ts).
import type { PyodideAPI } from "pyodide";
import runnerSource from "../../python/gw_runner.py?raw";
import { gradeCode, installRunner, runCode, traceCode } from "./host";
import type { WorkerRequest, WorkerResponse } from "./protocol";

declare const self: DedicatedWorkerGlobalScope;

let pyodide: Promise<PyodideAPI> | null = null;

async function boot(): Promise<PyodideAPI> {
  const base = new URL(`${import.meta.env.BASE_URL}pyodide/`, self.location.origin).href;
  const mod = (await import(/* @vite-ignore */ `${base}pyodide.mjs`)) as typeof import("pyodide");
  const py = await mod.loadPyodide({
    indexURL: base,
    // Optional packages (numpy, pandas, ...) are not bundled; fetch them from the
    // official Pyodide CDN only when a lesson explicitly asks for them.
    packageBaseUrl: `https://cdn.jsdelivr.net/pyodide/v${mod.version}/full/`,
    stdout: () => {},
    stderr: () => {},
  });
  installRunner(py, runnerSource);
  return py;
}

function getPyodide(): Promise<PyodideAPI> {
  if (!pyodide) pyodide = boot();
  return pyodide;
}

const reply = (message: WorkerResponse) => self.postMessage(message);

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const request = event.data;
  try {
    const py = await getPyodide();
    switch (request.type) {
      case "init":
        reply({ id: request.id, type: "ready", version: py.version });
        break;
      case "run":
        reply({ id: request.id, type: "run", result: runCode(py, request.code, request.stdin) });
        break;
      case "trace":
        reply({ id: request.id, type: "trace", result: traceCode(py, request.code, request.stdin, request.maxSteps) });
        break;
      case "grade":
        reply({ id: request.id, type: "grade", result: gradeCode(py, request.code, request.tests, request.stdin) });
        break;
      case "load-packages": {
        const loaded: string[] = [];
        await py.loadPackage(request.packages, { messageCallback: (msg: string) => loaded.push(msg) });
        reply({ id: request.id, type: "packages", messages: loaded });
        break;
      }
    }
  } catch (error) {
    reply({ id: request.id, type: "error", message: error instanceof Error ? error.message : String(error) });
  }
};
