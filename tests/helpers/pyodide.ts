// Loads Pyodide in Node with the same runner the browser worker uses.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { loadPyodide, type PyodideAPI } from "pyodide";
import { installRunner } from "../../src/python/host";

let instance: Promise<PyodideAPI> | null = null;

export function getPyodide(): Promise<PyodideAPI> {
  if (!instance) {
    instance = (async () => {
      const py = await loadPyodide();
      installRunner(py, readFileSync(resolve(import.meta.dirname, "../../python/gw_runner.py"), "utf8"));
      return py;
    })();
  }
  return instance;
}

export const projectRoot = resolve(import.meta.dirname, "../..");
