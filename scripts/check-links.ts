// Check every external URL referenced by content (sources and markdown links)
// and record the result in content/link-report.json. The app shows the
// check date next to sources; nothing is claimed as "checked" unless it is in
// this report.
//
// Usage:
//   npm run check:links                         # all content
//   npm run check:links -- content/stages/14-rag.yaml content/lessons/python/x.yaml
//   npm run check:links -- --only-new           # skip URLs already OK in the report
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { readContent } from "../src/content/load.ts";

interface LinkResult {
  ok: boolean;
  status: number | null;
  /** "ok" | "redirect" | "blocked" (403/429: site refuses bots — not necessarily broken) | "broken" | "error" */
  verdict: "ok" | "redirect" | "blocked" | "broken" | "error";
  finalUrl?: string;
  checkedAt: string;
  error?: string;
}

const root = resolve(import.meta.dirname, "..");
const reportPath = resolve(root, "content", "link-report.json");
const args = process.argv.slice(2);
const onlyNew = args.includes("--only-new");
const fileFilter = args.filter((a) => !a.startsWith("--")).map((f) => relative(root, resolve(f)).split(sep).join("/"));

const MD_LINK = /\]\((https?:\/\/[^)\s]+)\)/g;

function collectUrls(value: unknown, out: Set<string>) {
  if (typeof value === "string") {
    for (const m of value.matchAll(MD_LINK)) out.add(m[1]!);
  } else if (Array.isArray(value)) {
    value.forEach((v) => collectUrls(v, out));
  } else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      if (k === "url" && typeof v === "string" && /^https?:\/\//.test(v)) out.add(v);
      else collectUrls(v, out);
    }
  }
}

const { raw } = readContent(root);
const files = [...raw.stages, ...raw.lessons, ...raw.glossary, ...raw.projects, ...raw.interview, ...(raw.paths ? [raw.paths] : [])];
const urls = new Set<string>();
for (const f of files) {
  if (fileFilter.length && !fileFilter.includes(f.file)) continue;
  collectUrls(f.data, urls);
}

function readPrevious(): { checkedAt?: string; results: Record<string, LinkResult> } {
  if (!existsSync(reportPath)) return { results: {} };
  try {
    return JSON.parse(readFileSync(reportPath, "utf8"));
  } catch {
    return { results: {} }; // a partially written report is just a cache miss
  }
}
const previous = readPrevious();

const todo = [...urls].filter((u) => !(onlyNew && previous.results[u]?.ok));
console.log(`Checking ${todo.length} URL(s)${fileFilter.length ? ` from ${fileFilter.length} file(s)` : ""}…`);

async function check(url: string): Promise<LinkResult> {
  const checkedAt = new Date().toISOString();
  const attempt = async (method: "HEAD" | "GET") => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15_000);
    try {
      return await fetch(url, {
        method,
        redirect: "follow",
        signal: controller.signal,
        headers: { "user-agent": "Mozilla/5.0 (Groundwork link checker; +local)", accept: "text/html,application/xhtml+xml,*/*" },
      });
    } finally {
      clearTimeout(timer);
    }
  };
  try {
    let res = await attempt("HEAD");
    if (res.status === 405 || res.status === 403 || res.status === 404 || res.status >= 500) res = await attempt("GET");
    const status = res.status;
    const finalUrl = res.url !== url ? res.url : undefined;
    if (status >= 200 && status < 300) return { ok: true, status, verdict: finalUrl ? "redirect" : "ok", finalUrl, checkedAt };
    if (status === 403 || status === 429 || status === 401) return { ok: false, status, verdict: "blocked", finalUrl, checkedAt };
    return { ok: false, status, verdict: "broken", finalUrl, checkedAt };
  } catch (e) {
    return { ok: false, status: null, verdict: "error", error: (e as Error).message, checkedAt };
  }
}

const results: Record<string, LinkResult> = { ...previous.results };
const queue = [...todo];
const workers = Array.from({ length: 8 }, async () => {
  while (queue.length) {
    const url = queue.shift()!;
    results[url] = await check(url);
    const r = results[url];
    if (!r.ok) console.log(`  ${r.verdict.toUpperCase().padEnd(8)} ${r.status ?? "-"}  ${url}${r.error ? `  (${r.error})` : ""}`);
  }
});
await Promise.all(workers);

// Drop entries for URLs no longer referenced anywhere (only on full runs).
if (!fileFilter.length) {
  const all = new Set<string>();
  for (const f of files) collectUrls(f.data, all);
  for (const u of Object.keys(results)) if (!all.has(u)) delete results[u];
}

const sorted = Object.fromEntries(Object.entries(results).sort(([a], [b]) => a.localeCompare(b)));
writeFileSync(reportPath, JSON.stringify({ checkedAt: new Date().toISOString(), results: sorted }, null, 2) + "\n");
const values = todo.map((u) => results[u]!);
const count = (v: LinkResult["verdict"]) => values.filter((r) => r.verdict === v).length;
console.log(
  `Done: ${count("ok") + count("redirect")} ok (${count("redirect")} redirected), ${count("blocked")} blocked by the site, ${count("broken")} broken, ${count("error")} errors. Report: content/link-report.json`,
);
if (count("broken") > 0) process.exitCode = 1;
