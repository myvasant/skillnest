import { lazy, Suspense, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ScanSearch, Shapes } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { Card, PageHeader, cn } from "../../components/ui";
import { CodeView } from "../../components/CodeView";
import { useDocumentTitle } from "../../lib/hooks";
import { VisualizationBlock } from "./registry";
import { presets } from "./presets";

const CodeEditor = lazy(() => import("../../components/CodeEditor").then((m) => ({ default: m.CodeEditor })));
const PythonTracer = lazy(() => import("./PythonTracer").then((m) => ({ default: m.PythonTracer })));

function TracerWorkbench({ initial }: { initial: string }) {
  const [code, setCode] = useState(initial);
  const [traced, setTraced] = useState(initial);
  return (
    <div className="space-y-3 p-4">
      <div className="overflow-hidden rounded-lg border border-border">
        <Suspense fallback={<CodeView code={code} />}>
          <CodeEditor value={code} onChange={setCode} onRun={() => setTraced(code)} label="Code to step through. Control+Enter updates the trace." minLines={6} />
        </Suspense>
      </div>
      <button className="text-[13px] text-accent underline underline-offset-2" onClick={() => setTraced(code)}>
        Update the step-through with this code (Ctrl+Enter)
      </button>
      <div className="overflow-hidden rounded-lg border border-border">
        <Suspense fallback={<p className="p-4 text-sm text-muted">Loading…</p>}>
          <PythonTracer key={traced} code={traced} embedded maxSteps={600} />
        </Suspense>
      </div>
    </div>
  );
}

export function VisualExplorerPage() {
  useDocumentTitle("Visual explorer");
  const [params, setParams] = useSearchParams();
  const selected = presets.find((p) => p.id === params.get("v")) ?? presets[0]!;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Visual explorer"
        description="Interactive models of how things work. Every number shown is computed live — the Python step-through is a real trace of CPython, and the SQL joins match SQLite."
      />
      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <nav aria-label="Visualizations">
          <ul className="space-y-0.5">
            {presets.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => setParams({ v: p.id }, { replace: true })}
                  aria-current={p.id === selected.id ? "true" : undefined}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-[14px]",
                    p.id === selected.id ? "bg-surface shadow-card ring-1 ring-border" : "text-muted hover:bg-surface/70 hover:text-text",
                  )}
                >
                  {p.component === "python-tracer" ? <ScanSearch className="mt-0.5 size-4 shrink-0" aria-hidden /> : <Shapes className="mt-0.5 size-4 shrink-0" aria-hidden />}
                  {p.title}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight">{selected.title}</h2>
          <p className="mt-1 text-[14.5px] text-muted">{selected.summary}</p>
          <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[13px]">
            <span className="text-faint">Related:</span>
            {selected.concepts
              .filter((c) => curriculum.concepts[c])
              .map((c) => {
                const concept = curriculum.concepts[c]!;
                return (
                  <Link key={c} to={concept.lessonId ? `/learn/${concept.lessonId}` : `/concept/${c}`} className="text-accent underline underline-offset-2">
                    {concept.title}
                  </Link>
                );
              })}
          </p>
          {selected.component === "python-tracer" ? (
            <Card className="mt-4 overflow-hidden">
              <TracerWorkbench key={selected.id} initial={String(selected.props.code)} />
            </Card>
          ) : (
            <div key={selected.id}>
              <VisualizationBlock component={selected.component} props={selected.props} title={selected.title} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
