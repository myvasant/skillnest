// Copies the Pyodide runtime from node_modules into public/pyodide so the
// in-browser Python interpreter is served locally (no CDN needed for core
// lessons). Optional extra packages such as numpy are fetched from the
// Pyodide CDN on demand; see COST_AND_LICENSES.md.
import { copyFileSync, existsSync, mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "pyodide");
const target = join(root, "public", "pyodide");
const files = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json", "package.json"];

if (!existsSync(source)) {
  console.error("[copy-pyodide] node_modules/pyodide is missing. Run `npm install` first.");
  process.exit(1);
}
mkdirSync(target, { recursive: true });
let copied = 0;
for (const file of files) {
  const from = join(source, file);
  const to = join(target, file);
  if (existsSync(to) && statSync(to).size === statSync(from).size && statSync(to).mtimeMs >= statSync(from).mtimeMs) {
    continue;
  }
  copyFileSync(from, to);
  copied += 1;
}
console.log(`[copy-pyodide] runtime ready in public/pyodide (${copied} file(s) updated)`);
