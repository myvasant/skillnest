import { lazy, Suspense, useState } from "react";
import { CheckCircle2, Eye, Lightbulb, Play, RotateCcw, Send, XCircle } from "lucide-react";
import type { CodeItem } from "../../content/schema";
import { CodeView } from "../../components/CodeView";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, cn } from "../../components/ui";
import { feedbackFor } from "../../engine/feedback";
import { diffOutput, outputsMatch } from "../../engine/output";
import { python } from "../../python/client";
import type { GradeResult, RunResult } from "../../python/types";
import { clearCode, recordHint, recordSolutionViewed, saveCode } from "../../storage/actions";
import { progressStore, useProgressSelector } from "../../storage/store";
import { RunOutput } from "../code/RunOutput";
import { ItemFrame, type ItemProps } from "./shared";
import { reportAnswer } from "./record";

const CodeEditor = lazy(() => import("../../components/CodeEditor").then((m) => ({ default: m.CodeEditor })));

function OutputDiff({ actual, expected }: { actual: string; expected: string }) {
  const rows = diffOutput(actual, expected);
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-border text-[12.5px]">
      <div className="grid grid-cols-[2.5rem_1fr_1fr] bg-surface-2 px-2 py-1 font-semibold text-muted">
        <span>Line</span>
        <span>Expected</span>
        <span>Your output</span>
      </div>
      {rows.map((r) => (
        <div
          key={r.line}
          className={cn("grid grid-cols-[2.5rem_1fr_1fr] border-t border-border px-2 py-1 font-mono", r.kind !== "same" && "bg-danger-soft/50")}
        >
          <span className="text-faint">{r.line}</span>
          <span className="whitespace-pre-wrap">{r.expected ?? <em className="text-faint">(nothing)</em>}</span>
          <span className="whitespace-pre-wrap">{r.actual ?? <em className="text-faint">(missing)</em>}</span>
        </div>
      ))}
    </div>
  );
}

export function CodeExercise({ item, gid, mode, onAnswered }: ItemProps<CodeItem>) {
  const key = `item:${gid}`;
  const saved = useProgressSelector((p) => p.code[key]?.code);
  const fontSize = useProgressSelector((p) => p.settings.editorFontSize);
  const code = saved ?? item.starterCode;
  const [run, setRun] = useState<RunResult | null>(null);
  const [grade, setGrade] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState<"run" | "check" | null>(null);
  const [hintsShown, setHintsShown] = useState(0);
  const [showSolution, setShowSolution] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const locked = mode === "assessment" && submitted;

  const doRun = async () => {
    setBusy("run");
    setGrade(null);
    setRun(await python.run(code, { stdin: item.stdin }));
    setBusy(null);
  };

  const doCheck = async () => {
    setBusy("check");
    setRun(null);
    const result = await python.grade(code, item.tests, { stdin: item.stdin });
    setGrade(result);
    setBusy(null);
    if (result.run.status !== "completed") return; // timeouts/unavailable are not counted as attempts
    if (mode === "assessment") setSubmitted(true);
    reportAnswer(gid, mode, result.passed, onAnswered);
  };

  const revealHint = () => {
    setHintsShown((n) => n + 1);
    progressStore.update((p, now) => recordHint(p, gid, now));
  };

  const revealSolution = () => {
    setShowSolution(true);
    progressStore.update((p, now) => recordSolutionViewed(p, gid, now));
  };

  const messages = grade ? feedbackFor(item.feedback, grade.run, code) : [];
  const status = grade && grade.run.status === "completed" ? (grade.passed ? "correct" : "incorrect") : null;
  const showDiff =
    grade && !grade.passed && item.expectedOutput !== undefined && grade.run.status === "completed" && !outputsMatch(grade.run.stdout, item.expectedOutput);

  return (
    <ItemFrame item={item} gid={gid} status={status}>
      {item.stdin !== undefined && (
        <p className="mb-2 text-[13px] text-muted">
          Input provided to <code className="font-mono">input()</code>:{" "}
          <code className="rounded bg-surface-2 px-1 font-mono text-text">{item.stdin.replace(/\n/g, " ⏎ ")}</code>
        </p>
      )}
      <div className="overflow-hidden rounded-lg border border-border">
        {locked ? (
          <CodeView code={code} errorLine={grade?.run.error?.line ?? null} />
        ) : (
          <Suspense fallback={<CodeView code={code} />}>
            <CodeEditor
              value={code}
              onChange={(v) => progressStore.update((p, now) => saveCode(p, key, v, now))}
              onRun={doRun}
              errorLine={(grade?.run.error ?? run?.error)?.line ?? null}
              label={`Code editor for exercise. Control+Enter runs the code.`}
              minLines={Math.max(5, Math.min(14, item.starterCode.split("\n").length + 2))}
              fontSize={fontSize}
            />
          </Suspense>
        )}
        {run && <RunOutput result={run} />}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={doRun} loading={busy === "run"} disabled={locked || busy !== null} icon={<Play className="size-4" aria-hidden />}>
          Run
        </Button>
        <Button
          variant="primary"
          onClick={doCheck}
          loading={busy === "check"}
          disabled={locked || busy !== null}
          icon={mode === "assessment" ? <Send className="size-4" aria-hidden /> : <CheckCircle2 className="size-4" aria-hidden />}
        >
          {mode === "assessment" ? "Submit answer" : "Check my code"}
        </Button>
        {mode === "practice" && hintsShown < item.hints.length && (
          <Button variant="ghost" onClick={revealHint} icon={<Lightbulb className="size-4" aria-hidden />}>
            Hint {hintsShown + 1}/{item.hints.length}
          </Button>
        )}
        {mode === "practice" && saved !== undefined && saved !== item.starterCode && (
          <Button
            variant="ghost"
            onClick={() => {
              progressStore.update((p, now) => clearCode(p, key, now));
              setRun(null);
              setGrade(null);
            }}
            icon={<RotateCcw className="size-4" aria-hidden />}
          >
            Reset
          </Button>
        )}
        {mode === "practice" && !showSolution && (grade !== null || hintsShown === item.hints.length) && (
          <Button variant="ghost" onClick={revealSolution} icon={<Eye className="size-4" aria-hidden />}>
            Show solution
          </Button>
        )}
        <span className="text-[12px] text-faint">Ctrl/⌘ + Enter to run</span>
      </div>

      {hintsShown > 0 && (
        <ol className="mt-3 space-y-1.5">
          {item.hints.slice(0, hintsShown).map((h, i) => (
            <li key={i} className="flex gap-2 rounded-lg border border-info/25 bg-info-soft/60 px-3 py-2 text-[14px]">
              <Lightbulb className="mt-0.5 size-4 shrink-0 text-info" aria-hidden />
              <Markdown inline className="text-[14px]">
                {h}
              </Markdown>
            </li>
          ))}
        </ol>
      )}

      {grade && (
        <div className="mt-4 overflow-hidden rounded-lg border border-border" aria-live="polite">
          {grade.run.status === "completed" && (
            <div
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 text-sm font-semibold",
                grade.passed ? "bg-success-soft text-success" : "bg-danger-soft text-danger",
              )}
            >
              {grade.passed ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
              {grade.passed
                ? "All checks passed."
                : `${grade.tests.filter((t) => t.passed).length} of ${grade.tests.length} checks passed${grade.run.error ? " — and the program raised an error" : ""}.`}
            </div>
          )}
          {grade.tests.length > 0 && (
            <ul className="divide-y divide-border">
              {grade.tests.map((t) => (
                <li key={t.name} className="flex items-start gap-2 px-4 py-2 text-[14px]">
                  {t.passed ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="passed" />
                  ) : (
                    <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-label="failed" />
                  )}
                  <div>
                    <span className="font-medium">{t.name}</span>
                    {!t.passed && t.message && <p className="text-muted">{t.message}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {messages.length > 0 && (
            <div className="space-y-2 border-t border-border px-4 py-3">
              {messages.map((m) => (
                <p key={m} className="flex gap-2 text-[14px]">
                  <Badge tone="warning">Common mistake</Badge>
                  <span>{m}</span>
                </p>
              ))}
            </div>
          )}
          {showDiff && (
            <div className="border-t border-border px-4 py-3">
              <p className="text-[13px] font-medium text-muted">Expected vs. your output</p>
              <OutputDiff actual={grade.run.stdout} expected={item.expectedOutput!} />
            </div>
          )}
          {(grade.run.error || grade.run.status !== "completed" || (grade.run.stdout && !showDiff)) && <RunOutput result={grade.run} />}
          {(grade.passed || mode === "assessment") && (
            <div className="border-t border-border px-4 py-3 text-[14px]">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-muted">Why it works</p>
              <Markdown className="mt-0.5 text-[14px]">{item.explanation}</Markdown>
            </div>
          )}
        </div>
      )}

      {(showSolution || (mode === "assessment" && submitted)) && (
        <div className="mt-4 overflow-hidden rounded-lg border border-violet/30">
          <div className="flex items-center justify-between bg-violet-soft px-4 py-2 text-[13px] font-semibold text-violet">
            Reference solution
            {mode === "practice" && <span className="font-normal text-muted">Try retyping it from memory afterwards.</span>}
          </div>
          <CodeView code={item.solution} />
          <div className="border-t border-border px-4 py-3">
            <Markdown className="text-[14px]">{item.explanation}</Markdown>
          </div>
        </div>
      )}
    </ItemFrame>
  );
}
