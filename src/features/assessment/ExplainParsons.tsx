import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Plus, RotateCcw, X } from "lucide-react";
import type { ExplainItem as Explain, ParsonsItem as Parsons } from "../../content/schema";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, cn } from "../../components/ui";
import { outputsMatch } from "../../engine/output";
import { python } from "../../python/client";
import type { RunResult } from "../../python/types";
import { RunOutput } from "../code/RunOutput";
import { ItemFrame, Verdict, seededShuffle, type ItemProps } from "./shared";
import { reportAnswer } from "./record";

export const EXPLAIN_PASS = 0.75;

/** Open-ended explanation, self-assessed against a transparent rubric. */
export function ExplainItem({ item, gid, mode, onAnswered }: ItemProps<Explain>) {
  const [text, setText] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [checked, setChecked] = useState<boolean[]>(() => item.rubric.map(() => false));
  const [done, setDone] = useState<number | null>(null);

  const submit = () => {
    const score = checked.filter(Boolean).length / item.rubric.length;
    setDone(score);
    reportAnswer(gid, mode, score >= EXPLAIN_PASS, onAnswered);
  };

  return (
    <ItemFrame item={item} gid={gid} status={done === null ? null : done >= EXPLAIN_PASS ? "correct" : "incorrect"}>
      <label htmlFor={`${gid}-text`} className="text-[13px] font-medium text-muted">
        Your explanation
      </label>
      <textarea
        id={`${gid}-text`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        disabled={revealed}
        className="mt-1 w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-[14.5px] leading-relaxed focus:border-accent focus:outline-none"
        placeholder="Write it as if teaching someone else. Aim for 3–5 sentences."
      />
      {!revealed && (
        <Button className="mt-2" variant="primary" onClick={() => setRevealed(true)} disabled={text.trim().length < 20}>
          Compare with the rubric
        </Button>
      )}
      {revealed && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-border p-3">
            <p className="mb-2 flex items-center gap-2 text-[13px] font-semibold">
              Rubric <Badge tone="info">Self-assessed</Badge>
            </p>
            <p className="mb-2 text-[12.5px] text-muted">
              Tick each point your explanation actually covers. Be honest — this only affects your own review schedule.
            </p>
            <ul className="space-y-2">
              {item.rubric.map((r, i) => (
                <li key={r}>
                  <label className="flex cursor-pointer gap-2 text-[14px]">
                    <input
                      type="checkbox"
                      checked={checked[i]}
                      disabled={done !== null}
                      onChange={(e) => setChecked((c) => c.map((v, j) => (j === i ? e.target.checked : v)))}
                      className="mt-1 accent-[var(--gw-accent)]"
                    />
                    {r}
                  </label>
                </li>
              ))}
            </ul>
            {done === null && (
              <Button className="mt-3" variant="primary" size="sm" onClick={submit}>
                Record self-assessment
              </Button>
            )}
          </div>
          <div className="rounded-lg border border-violet/30 bg-violet-soft/40 p-3">
            <p className="mb-1 text-[13px] font-semibold text-violet">Model answer</p>
            <Markdown className="text-[14px]">{item.modelAnswer}</Markdown>
          </div>
        </div>
      )}
      {done !== null && (
        <Verdict
          correct={done >= EXPLAIN_PASS}
          feedback={`You covered ${Math.round(done * item.rubric.length)} of ${item.rubric.length} rubric points.${done < EXPLAIN_PASS ? " Rewrite your explanation including the missing points — explaining is one of the strongest ways to learn." : ""}`}
          explanation={item.explanation}
          extra={
            mode === "practice" && done < EXPLAIN_PASS ? (
              <Button
                size="sm"
                className="mt-3"
                icon={<RotateCcw className="size-3.5" aria-hidden />}
                onClick={() => {
                  setRevealed(false);
                  setDone(null);
                  setChecked(item.rubric.map(() => false));
                }}
              >
                Rewrite
              </Button>
            ) : null
          }
        />
      )}
    </ItemFrame>
  );
}

/** Parsons problem: build the program from given lines (keyboard and screen-reader friendly, no drag-and-drop needed). */
export function ParsonsItem({ item, gid, mode, onAnswered }: ItemProps<Parsons>) {
  const pool = useMemo(() => {
    const lines = item.solution
      .replace(/\n$/, "")
      .split("\n")
      .filter((l) => l.trim());
    return seededShuffle(
      [...lines, ...item.distractors].map((text, i) => ({ id: i, text })),
      item.id,
    );
  }, [item]);
  const [chosen, setChosen] = useState<number[]>([]);
  const [result, setResult] = useState<{ correct: boolean; run?: RunResult } | null>(null);
  const [busy, setBusy] = useState(false);
  const available = pool.filter((p) => !chosen.includes(p.id));
  const program = chosen.map((id) => pool.find((p) => p.id === id)!.text).join("\n");

  const move = (from: number, to: number) =>
    setChosen((c) => {
      if (to < 0 || to >= c.length) return c;
      const next = [...c];
      [next[from], next[to]] = [next[to]!, next[from]!];
      return next;
    });

  const check = async () => {
    setBusy(true);
    let correct: boolean;
    let run: RunResult | undefined;
    if (item.expectedOutput !== undefined) {
      run = await python.run(program);
      if (run.status !== "completed") {
        setResult({ correct: false, run });
        setBusy(false);
        return;
      }
      correct = run.ok && outputsMatch(run.stdout, item.expectedOutput);
    } else {
      correct = program.trim() === item.solution.trim();
    }
    setResult({ correct, run });
    setBusy(false);
    reportAnswer(gid, mode, correct, onAnswered);
  };

  return (
    <ItemFrame item={item} gid={gid} status={result ? (result.correct ? "correct" : "incorrect") : null}>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[12.5px] font-semibold uppercase tracking-wide text-muted">Available lines</p>
          <ul className="min-h-24 space-y-1.5 rounded-lg border border-dashed border-border-strong p-2">
            {available.length === 0 && <li className="p-2 text-[13px] italic text-faint">All lines used.</li>}
            {available.map((line) => (
              <li key={line.id}>
                <button
                  type="button"
                  disabled={Boolean(result)}
                  onClick={() => setChosen((c) => [...c, line.id])}
                  className="flex w-full items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5 text-left font-mono text-[13px] hover:border-accent disabled:opacity-60"
                >
                  <Plus className="size-3.5 shrink-0 text-accent" aria-hidden />
                  <span className="whitespace-pre">{line.text}</span>
                  <span className="sr-only">add to program</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="mb-1.5 text-[12.5px] font-semibold uppercase tracking-wide text-muted">Your program</p>
          <ol className="min-h-24 space-y-1.5 rounded-lg border border-border bg-code p-2">
            {chosen.length === 0 && <li className="p-2 text-[13px] italic text-faint">Click lines on the left to add them here, in order.</li>}
            {chosen.map((id, i) => (
              <li key={id} className="flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1">
                <span className="w-5 text-right font-mono text-[11px] text-faint">{i + 1}</span>
                <code className="flex-1 whitespace-pre font-mono text-[13px]">{pool.find((p) => p.id === id)!.text}</code>
                {!result && (
                  <>
                    <Button size="sm" variant="ghost" aria-label="Move up" onClick={() => move(i, i - 1)} disabled={i === 0}>
                      <ArrowUp className="size-3.5" aria-hidden />
                    </Button>
                    <Button size="sm" variant="ghost" aria-label="Move down" onClick={() => move(i, i + 1)} disabled={i === chosen.length - 1}>
                      <ArrowDown className="size-3.5" aria-hidden />
                    </Button>
                    <Button size="sm" variant="ghost" aria-label="Remove line" onClick={() => setChosen((c) => c.filter((x) => x !== id))}>
                      <X className="size-3.5" aria-hidden />
                    </Button>
                  </>
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
      {!result && (
        <Button className="mt-3" variant="primary" onClick={check} loading={busy} disabled={chosen.length === 0}>
          Check order
        </Button>
      )}
      {result && (
        <Verdict
          correct={result.correct}
          feedback={
            result.correct
              ? item.expectedOutput !== undefined
                ? "Your program runs and produces the expected output."
                : null
              : item.expectedOutput !== undefined
                ? "Your arrangement does not produce the expected output. Check the order: is every name assigned before it is used? Did a distractor sneak in?"
                : "That order doesn't match a working program."
          }
          explanation={item.explanation}
          extra={
            <>
              {result.run && !result.correct && <RunOutput result={result.run} className={cn("mt-3 rounded-lg border")} compact />}
              {mode === "practice" && !result.correct && (
                <Button size="sm" className="mt-3" icon={<RotateCcw className="size-3.5" aria-hidden />} onClick={() => setResult(null)}>
                  Try again
                </Button>
              )}
            </>
          }
        />
      )}
    </ItemFrame>
  );
}
