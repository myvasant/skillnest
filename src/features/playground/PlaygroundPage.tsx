import { lazy, Suspense, useEffect, useState } from "react";
import { FolderOpen, PackagePlus, Play, Plus, RotateCcw, Save, ScanSearch, Trash2 } from "lucide-react";
import { CodeView } from "../../components/CodeView";
import { Badge, Button, Card, PageHeader, cn } from "../../components/ui";
import { useDocumentTitle, useOnline } from "../../lib/hooks";
import { python, DEFAULT_TIMEOUT_MS } from "../../python/client";
import type { RunResult } from "../../python/types";
import { deleteSnippet, saveCode, saveSnippet } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";
import { RunOutput } from "../code/RunOutput";

const CodeEditor = lazy(() => import("../../components/CodeEditor").then((m) => ({ default: m.CodeEditor })));
const PythonTracer = lazy(() => import("../visualizations/PythonTracer").then((m) => ({ default: m.PythonTracer })));

const DRAFT_KEY = "playground:draft";

export const EXAMPLES: { title: string; code: string; stdin?: string }[] = [
  { title: "Hello, names and objects", code: 'greeting = "Hello"\nname = "Ada"\nmessage = greeting + ", " + name + "!"\nprint(message)\n' },
  { title: "Aliasing a list", code: "a = [1, 2, 3]\nb = a\nb.append(4)\nprint(a)\nprint(a is b)\n" },
  {
    title: "Reading input",
    code: 'name = input("What is your name? ")\nage = int(input("How old are you? "))\nprint(f"{name} will be {age + 1} next year.")\n',
    stdin: "Grace\n36\n",
  },
  { title: "A function call", code: "def area(width, height):\n    result = width * height\n    return result\n\nprint(area(3, 4))\n" },
  { title: "Recursion: factorial", code: "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n\nprint(factorial(5))\n" },
  {
    title: "Counting words with a dict",
    code: 'text = "the cat and the hat and the bat"\ncounts = {}\nfor word in text.split():\n    counts[word] = counts.get(word, 0) + 1\nprint(counts)\n',
  },
];

const PACKAGES = ["numpy", "pandas", "matplotlib", "scikit-learn", "networkx", "sympy"];

export function PlaygroundPage() {
  useDocumentTitle("Playground");
  const progress = useProgress();
  const online = useOnline();
  const code = progress.code[DRAFT_KEY]?.code ?? EXAMPLES[0]!.code;
  const [stdin, setStdin] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [tracing, setTracing] = useState(false);
  const [snippetId, setSnippetId] = useState<string | null>(null);
  const [title, setTitle] = useState("Untitled snippet");
  const [pkgMessage, setPkgMessage] = useState<string | null>(null);
  const [loadingPkg, setLoadingPkg] = useState<string | null>(null);

  useEffect(() => {
    void python.preload().catch(() => undefined);
  }, []);

  const setCode = (value: string) => progressStore.update((p, now) => saveCode(p, DRAFT_KEY, value, now));
  const run = async () => {
    setRunning(true);
    setResult(await python.run(code, { stdin }));
    setRunning(false);
  };

  const save = () => {
    const id = snippetId ?? `s-${Date.now().toString(36)}`;
    progressStore.update((p, now) => saveSnippet(p, { id, title: title.trim() || "Untitled snippet", code }, now));
    setSnippetId(id);
  };

  const loadPackage = async (pkg: string) => {
    setLoadingPkg(pkg);
    const r = await python.loadPackages([pkg]);
    setPkgMessage(r.ok ? `Loaded ${pkg}. You can now import it.` : `Could not load ${pkg}: ${r.message}`);
    setLoadingPkg(null);
  };

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Python playground"
        description="Real CPython 3.14 compiled to WebAssembly (Pyodide), running in an isolated worker in your browser. Experiment freely — nothing here can harm your computer or your progress."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
              <label className="sr-only" htmlFor="snippet-title">
                Snippet title
              </label>
              <input
                id="snippet-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="h-8 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-2 text-[14px] font-medium hover:border-border focus:border-accent focus:outline-none"
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setTracing((t) => !t)}
                aria-pressed={tracing}
                icon={<ScanSearch className="size-3.5" aria-hidden />}
              >
                Step through
              </Button>
              <Button size="sm" variant="ghost" onClick={save} icon={<Save className="size-3.5" aria-hidden />}>
                Save
              </Button>
              <Button size="sm" variant="primary" onClick={run} loading={running} icon={<Play className="size-3.5" aria-hidden />}>
                Run
              </Button>
            </div>
            <Suspense fallback={<CodeView code={code} />}>
              <CodeEditor
                value={code}
                onChange={setCode}
                onRun={run}
                errorLine={result?.error?.line ?? null}
                label="Playground code editor. Control+Enter runs."
                minLines={16}
                fontSize={progress.settings.editorFontSize}
              />
            </Suspense>
            <details className="border-t border-border" open={stdin.length > 0}>
              <summary className="cursor-pointer px-4 py-2 text-[13px] font-medium text-muted hover:text-text">
                Input (stdin) — one line per input() call
              </summary>
              <textarea
                value={stdin}
                onChange={(e) => setStdin(e.target.value)}
                rows={3}
                aria-label="Program input, one line per input() call"
                className="w-full border-t border-border bg-code px-4 py-2 font-mono text-[13px] focus:outline-none"
                placeholder={"Ada\n36"}
              />
            </details>
            {result && <RunOutput result={result} />}
          </Card>
          {tracing && (
            <Card className="overflow-hidden">
              <Suspense fallback={<p className="p-4 text-sm text-muted">Loading…</p>}>
                <PythonTracer code={code} stdin={stdin} embedded maxSteps={600} />
              </Suspense>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Examples</h2>
            <ul className="space-y-0.5">
              {EXAMPLES.map((ex) => (
                <li key={ex.title}>
                  <button
                    className="w-full rounded-md px-2 py-1.5 text-left text-[13.5px] hover:bg-surface-2"
                    onClick={() => {
                      setCode(ex.code);
                      setStdin(ex.stdin ?? "");
                      setResult(null);
                      setSnippetId(null);
                      setTitle(ex.title);
                    }}
                  >
                    {ex.title}
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">Saved snippets</h2>
              <Button
                size="sm"
                variant="ghost"
                aria-label="New snippet"
                onClick={() => {
                  setSnippetId(null);
                  setTitle("Untitled snippet");
                  setCode("");
                  setResult(null);
                }}
              >
                <Plus className="size-4" aria-hidden />
              </Button>
            </div>
            {progress.snippets.length === 0 ? (
              <p className="text-[13px] text-muted">Snippets you save are stored locally and included in progress exports.</p>
            ) : (
              <ul className="space-y-0.5">
                {progress.snippets.map((s) => (
                  <li key={s.id} className={cn("flex items-center gap-1 rounded-md", snippetId === s.id && "bg-accent-soft")}>
                    <button
                      className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-[13.5px]"
                      onClick={() => {
                        setCode(s.code);
                        setSnippetId(s.id);
                        setTitle(s.title);
                        setResult(null);
                      }}
                    >
                      <FolderOpen className="size-3.5 shrink-0 text-muted" aria-hidden />
                      <span className="truncate">{s.title}</span>
                    </button>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Delete ${s.title}`}
                      onClick={() => {
                        progressStore.update((p, now) => deleteSnippet(p, s.id, now));
                        if (snippetId === s.id) setSnippetId(null);
                      }}
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="p-4">
            <h2 className="mb-1 text-[13px] font-semibold uppercase tracking-wide text-muted">Optional packages</h2>
            <p className="mb-2 text-[12.5px] text-muted">
              Downloaded once from the official Pyodide CDN (needs internet; numpy ≈ 3 MB, pandas ≈ 12 MB). The standard library needs no download.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {PACKAGES.map((pkg) => (
                <Button
                  key={pkg}
                  size="sm"
                  disabled={!online || loadingPkg !== null}
                  loading={loadingPkg === pkg}
                  onClick={() => loadPackage(pkg)}
                  icon={<PackagePlus className="size-3.5" aria-hidden />}
                >
                  {pkg}
                </Button>
              ))}
            </div>
            {!online && <p className="mt-2 text-[12.5px] text-warning">You're offline, so packages can't be downloaded.</p>}
            {pkgMessage && <p className="mt-2 text-[12.5px] text-muted">{pkgMessage}</p>}
          </Card>
          <Card className="p-4 text-[12.5px] text-muted">
            <h2 className="mb-1 text-[13px] font-semibold uppercase tracking-wide">Runtime limits</h2>
            <ul className="list-disc space-y-1 pl-4">
              <li>Programs are stopped after {DEFAULT_TIMEOUT_MS / 1000} s, and the runtime restarts.</li>
              <li>Output is capped at 200,000 characters.</li>
              <li>No real files, network sockets, threads or subprocesses; the file system is virtual and temporary.</li>
              <li>input() reads from the Input box above.</li>
            </ul>
            <Button
              size="sm"
              className="mt-3"
              onClick={() => void python.restart().catch(() => undefined)}
              icon={<RotateCcw className="size-3.5" aria-hidden />}
            >
              Restart runtime
            </Button>
            <p className="mt-2">
              <Badge tone="neutral">Pyodide {python.version ?? "not started"}</Badge>
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
