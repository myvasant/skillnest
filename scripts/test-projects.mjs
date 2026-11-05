// Verify project starter kits with native Python:
//   1. every reference solution passes its project's tests  (GW_TARGET=solution)
//   2. every starter fails at least one test                (GW_TARGET=starter)
// Usage: node scripts/test-projects.mjs [project-id ...]
// Uses .venv if present, otherwise `python` on PATH.
import { existsSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const venvPython = process.platform === "win32" ? join(root, ".venv", "Scripts", "python.exe") : join(root, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : "python";
const projectsDir = join(root, "projects");
const only = process.argv.slice(2);

const kits = existsSync(projectsDir)
  ? readdirSync(projectsDir).filter((d) => statSync(join(projectsDir, d)).isDirectory() && existsSync(join(projectsDir, d, "tests")) && (!only.length || only.includes(d)))
  : [];

if (!kits.length) {
  console.log("No project starter kits found.");
  process.exit(0);
}

let failed = 0;
for (const kit of kits) {
  const dir = join(projectsDir, kit);
  const run = (target) =>
    spawnSync(python, ["-m", "pytest", dir, "-q", "-p", "no:cacheprovider", "-m", "not network"], {
      cwd: root,
      env: { ...process.env, GW_TARGET: target, PYTHONDONTWRITEBYTECODE: "1" },
      encoding: "utf8",
    });
  const solution = run("solution");
  const starter = run("starter");
  const solutionOk = solution.status === 0;
  // Exit code 1 = some tests failed (what we want for a starter). 5 = no tests collected.
  const starterFails = starter.status === 1;
  const summary = (r) => (r.stdout || r.stderr || "").trim().split("\n").filter(Boolean).at(-1) ?? "";
  console.log(`${solutionOk && starterFails ? "ok  " : "FAIL"} ${kit.padEnd(32)} solution: ${summary(solution)} | starter: ${summary(starter)}`);
  if (!solutionOk) {
    failed++;
    console.log(solution.stdout.split("\n").slice(-40).join("\n"));
  } else if (!starterFails) {
    failed++;
    console.log(`  starter did not fail any test (exit ${starter.status}) — the tests may not be testing anything.`);
  }
}
if (failed) {
  console.log(`\n${failed} project kit(s) failed verification.`);
  process.exit(1);
}
console.log(`\nAll ${kits.length} project kit(s) verified.`);
