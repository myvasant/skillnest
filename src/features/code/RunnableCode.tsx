// A lesson code example: static by default, editable and runnable when the
// block is marked runnable. Edits are kept per example in local progress.
import { lazy, Suspense, useState } from "react";
import { BadgeCheck, Keyboard, Play, RotateCcw, ScanSearch } from "lucide-react";
import type { CodeBlock } from "../../content/schema";
import { CodeView } from "../../components/CodeView";
import { Badge, Button, cn } from "../../components/ui";
import { Markdown } from "../../components/Markdown";
import { python } from "../../python/client";
import type { RunResult } from "../../python/types";
import { progressStore, useProgressSelector } from "../../storage/store";
import { clearCode, saveCode } from "../../storage/actions";
import { RunOutput } from "./RunOutput";

const CodeEditor = lazy(() => import("../../components/CodeEditor").then((m) => ({ default: m.CodeEditor })));
const PythonTracer = lazy(() => import("../visualizations/PythonTracer").then((m) => ({ default: m.PythonTracer })));

export function VerificationBadge({ block }: { block: CodeBlock }) {
  if (block.language !== "python") return null;
  if (block.status === "illustrative") return <Badge tone="neutral">Illustrative — not executed</Badge>;
  if (block.status === "pseudocode") return <Badge tone="neutral">Pseudocode</Badge>;
  if (block.expectedOutput !== undefined || block.expectError) {
    return (
      <Badge tone="success" title="This example is executed by the automated content tests and its output is checked.">
        <BadgeCheck className="size-3" aria-hidden /> Verified output
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" title="Executed by the content tests to check it runs without errors.">
      Runs cleanly
    </Badge>
  );
}

export function RunnableCode({ block, storageKey }: { block: CodeBlock; storageKey: string }) {
  const saved = useProgressSelector((p) => p.code[storageKey]?.code);
  const fontSize = useProgressSelector((p) => p.settings.editorFontSize);
  const [editing, setEditing] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [tracing, setTracing] = useState(false);
  const code = saved ?? block.code;
  const modified = saved !== undefined && saved !== block.code;

  const run = async () => {
    setRunning(true);
    setResult(await python.run(code, { stdin: block.stdin }));
    setRunning(false);
  };

  const reset = () => {
    progressStore.update((p, now) => clearCode(p, storageKey, now));
    setResult(null);
  };

  const showAnnotations = block.annotations.length > 0;
  const runnable = block.runnable && block.language === "python";

  return (
    <figure className="not-prose my-5 overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <span className="font-mono uppercase tracking-wide">{block.language}</span>
          <VerificationBadge block={block} />
          {modified && <Badge tone="warning">Edited</Badge>}
        </div>
        {runnable && (
          <div className="flex items-center gap-1">
            {!editing && (
              <Button size="sm" variant="ghost" icon={<Keyboard className="size-3.5" aria-hidden />} onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              icon={<ScanSearch className="size-3.5" aria-hidden />}
              onClick={() => setTracing((t) => !t)}
              aria-pressed={tracing}
            >
              Step through
            </Button>
            {modified && (
              <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" aria-hidden />} onClick={reset}>
                Reset
              </Button>
            )}
            <Button size="sm" variant="primary" icon={<Play className="size-3.5" aria-hidden />} onClick={run} loading={running}>
              Run
            </Button>
          </div>
        )}
      </div>
      {editing && runnable ? (
        <Suspense fallback={<CodeView code={code} />}>
          <CodeEditor
            value={code}
            onChange={(v) => progressStore.update((p, now) => saveCode(p, storageKey, v, now))}
            onRun={run}
            errorLine={result?.error?.line ?? null}
            label="Editable example code. Press Control+Enter to run."
            minLines={Math.min(code.split("\n").length, 12)}
            fontSize={fontSize}
          />
        </Suspense>
      ) : (
        <CodeView code={code} language={block.language} errorLine={result?.error?.line ?? null} />
      )}
      {showAnnotations && !modified && (
        <ol className="space-y-1.5 border-t border-border bg-surface-2/50 px-4 py-3 text-[13.5px]">
          {block.annotations.map((a) => (
            <li key={`${a.line}-${a.text}`} className="flex gap-3">
              <span className="mt-0.5 inline-flex h-5 min-w-9 items-center justify-center rounded bg-surface-3 font-mono text-[11px] text-muted">
                L{a.line}
              </span>
              <Markdown inline className="text-[13.5px] leading-relaxed text-text">
                {a.text}
              </Markdown>
            </li>
          ))}
        </ol>
      )}
      {result && <RunOutput result={result} />}
      {tracing && runnable && (
        <div className="border-t border-border">
          <Suspense fallback={<p className="p-4 text-sm text-muted">Loading step-through…</p>}>
            <PythonTracer code={code} stdin={block.stdin} embedded />
          </Suspense>
        </div>
      )}
      {block.caption && (
        <figcaption className={cn("border-t border-border px-4 py-2 text-[13px] text-muted")}>
          <Markdown inline className="text-[13px] text-muted">
            {block.caption}
          </Markdown>
        </figcaption>
      )}
    </figure>
  );
}
