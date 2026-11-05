import { Link } from "react-router";
import { AlertTriangle, CircleCheck, Clock, Lightbulb, WifiOff } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { explainError, TIMEOUT_EXPLANATION, type ErrorExplanation } from "../../engine/errors";
import type { RunResult } from "../../python/types";
import { cn } from "../../components/ui";

function StdoutView({ result }: { result: RunResult }) {
  const parts: { text: string; input?: boolean }[] = [];
  let at = 0;
  for (const ev of result.events) {
    parts.push({ text: result.stdout.slice(at, ev.at) });
    parts.push({ text: `${ev.value}\n`, input: true });
    at = ev.at;
  }
  parts.push({ text: result.stdout.slice(at) });
  return (
    <pre className="scrollbar-thin max-h-72 overflow-auto whitespace-pre-wrap break-words px-4 py-3 font-mono text-[13px] leading-relaxed text-text">
      {parts.map((p, i) =>
        p.input ? (
          <span key={i} className="text-info" title="Value read by input()">
            {p.text}
          </span>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </pre>
  );
}

export function Explanation({ explanation }: { explanation: ErrorExplanation }) {
  const lessonId = explanation.learnMore ? curriculum.concepts[explanation.learnMore.conceptId]?.lessonId : null;
  return (
    <div className="rounded-lg border border-warning/30 bg-warning-soft/60 px-4 py-3 text-sm">
      <p className="flex items-center gap-2 font-semibold text-text">
        <Lightbulb className="size-4 text-warning" aria-hidden />
        {explanation.title}
      </p>
      <p className="mt-1.5 text-muted">{explanation.meaning}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-text">
        {explanation.fixes.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      {explanation.learnMore && (
        <p className="mt-2 text-[13px] text-muted">
          Learn more:{" "}
          <Link className="text-accent underline underline-offset-2" to={lessonId ? `/learn/${lessonId}` : `/concept/${explanation.learnMore.conceptId}`}>
            {explanation.learnMore.label}
          </Link>
        </p>
      )}
    </div>
  );
}

export function RunOutput({ result, className, compact }: { result: RunResult; className?: string; compact?: boolean }) {
  const hasOut = result.stdout.length > 0;
  return (
    <div className={cn("border-t border-border bg-surface", className)} aria-live="polite">
      <div className="flex items-center justify-between gap-2 border-b border-border/70 px-4 py-1.5 text-[12px] text-muted">
        <span className="font-medium uppercase tracking-wide">Output</span>
        {result.status === "completed" && (
          <span className={cn("inline-flex items-center gap-1", result.ok ? "text-success" : "text-danger")}>
            {result.ok ? <CircleCheck className="size-3.5" aria-hidden /> : <AlertTriangle className="size-3.5" aria-hidden />}
            {result.ok ? "Finished" : "Stopped with an error"} · {result.durationMs < 1 ? "<1" : Math.round(result.durationMs)} ms
          </span>
        )}
      </div>
      {hasOut && <StdoutView result={result} />}
      {!hasOut && result.status === "completed" && result.ok && <p className="px-4 py-3 text-[13px] italic text-faint">The program ran but printed nothing.</p>}
      {result.stderr && (
        <pre className="scrollbar-thin max-h-40 overflow-auto whitespace-pre-wrap border-t border-border/70 px-4 py-2 font-mono text-[12.5px] text-warning">
          {result.stderr}
        </pre>
      )}
      {result.error && (
        <div className="space-y-3 border-t border-border/70 px-4 py-3">
          <div>
            <p className="font-mono text-[13px] font-semibold text-danger">
              {result.error.type}: {result.error.message}
              {result.error.line ? <span className="font-normal text-muted"> (line {result.error.line})</span> : null}
            </p>
            <details className="mt-1 text-[12.5px] text-muted">
              <summary className="cursor-pointer select-none hover:text-text">Full traceback</summary>
              <pre className="mt-1 whitespace-pre-wrap font-mono text-[12px] text-text">{result.error.traceback}</pre>
            </details>
          </div>
          {!compact && <Explanation explanation={explainError(result.error)} />}
        </div>
      )}
      {result.status === "timeout" && (
        <div className="space-y-3 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium text-danger">
            <Clock className="size-4" aria-hidden /> {result.hostMessage}
          </p>
          <Explanation explanation={TIMEOUT_EXPLANATION} />
        </div>
      )}
      {result.status === "unavailable" && (
        <p className="flex items-start gap-2 px-4 py-3 text-sm text-danger">
          <WifiOff className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{result.hostMessage} Reload the page to retry. Lessons, quizzes and your progress still work without the Python runtime.</span>
        </p>
      )}
    </div>
  );
}
