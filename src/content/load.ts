// Node-only: read every YAML file under content/ and compile it.
// Used by the Vite plugin, the validate-content CLI and the test-suite.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { parse, YAMLParseError } from "yaml";
import { compileContent, type CompiledContent, type RawContent, type RawFile, type ValidationIssue } from "./build.ts";

function yamlFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...yamlFiles(full));
    else if (name.endsWith(".yaml") || name.endsWith(".yml")) out.push(full);
  }
  return out;
}

export function readContent(root: string): { raw: RawContent; parseIssues: ValidationIssue[]; files: string[] } {
  const contentDir = join(root, "content");
  const parseIssues: ValidationIssue[] = [];
  const files: string[] = [];
  const read = (full: string): RawFile | null => {
    const file = relative(root, full).split(sep).join("/");
    files.push(full);
    try {
      return { file, data: parse(readFileSync(full, "utf8"), { prettyErrors: true, uniqueKeys: true }) };
    } catch (e) {
      const message = e instanceof YAMLParseError ? e.message : String(e);
      parseIssues.push({ severity: "error", file, path: "", message: `YAML parse error: ${message}` });
      return null;
    }
  };
  const many = (dir: string) =>
    yamlFiles(join(contentDir, dir))
      .map(read)
      .filter((f): f is RawFile => f !== null);
  const one = (name: string) => (existsSync(join(contentDir, name)) ? read(join(contentDir, name)) : null);
  let linkReport: RawContent["linkReport"];
  const reportPath = join(contentDir, "link-report.json");
  if (existsSync(reportPath)) {
    try {
      linkReport = JSON.parse(readFileSync(reportPath, "utf8")).results;
    } catch {
      linkReport = undefined; // being rewritten by the link checker; treat as absent
    }
  }
  const raw: RawContent = {
    linkReport,
    stages: many("stages"),
    lessons: many("lessons"),
    glossary: many("glossary"),
    paths: one("paths.yaml"),
    projects: many("projects"),
    interview: many("interview"),
  };
  return { raw, parseIssues, files };
}

export function loadContent(root: string): CompiledContent & { files: string[] } {
  const { raw, parseIssues, files } = readContent(root);
  const compiled = compileContent(raw);
  compiled.issues.unshift(...parseIssues);
  return { ...compiled, files };
}

export function formatIssues(issues: ValidationIssue[]): string {
  return issues.map((i) => `${i.severity === "error" ? "ERROR" : "warn "} ${i.file}${i.path ? ` @ ${i.path}` : ""}: ${i.message}`).join("\n");
}
