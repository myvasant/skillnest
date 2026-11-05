import type { ReactNode } from "react";
import { CheckCircle2, CircleHelp, Code2, Bug, ListOrdered, MessageSquareText, Telescope, ToggleLeft, XCircle } from "lucide-react";
import type { Item, Skill } from "../../content/schema";
import { Markdown } from "../../components/Markdown";
import { Badge, cn } from "../../components/ui";

export type ItemMode = "practice" | "assessment";

export interface ItemProps<T extends Item> {
  item: T;
  gid: string;
  mode: ItemMode;
  /** Called once per graded attempt. In practice mode the item also records the attempt itself. */
  onAnswered?: (correct: boolean) => void;
}

const typeMeta: Record<Item["type"], { label: string; icon: ReactNode }> = {
  mcq: { label: "Multiple choice", icon: <CircleHelp className="size-3.5" aria-hidden /> },
  "true-false": { label: "True or false", icon: <ToggleLeft className="size-3.5" aria-hidden /> },
  "predict-output": { label: "Predict the output", icon: <Telescope className="size-3.5" aria-hidden /> },
  code: { label: "Coding exercise", icon: <Code2 className="size-3.5" aria-hidden /> },
  debug: { label: "Debugging exercise", icon: <Bug className="size-3.5" aria-hidden /> },
  explain: { label: "Explain it", icon: <MessageSquareText className="size-3.5" aria-hidden /> },
  parsons: { label: "Arrange the code", icon: <ListOrdered className="size-3.5" aria-hidden /> },
};

export const skillLabel: Record<Skill, string> = {
  recognition: "Recognition",
  explanation: "Explanation",
  prediction: "Prediction",
  implementation: "Implementation",
  debugging: "Debugging",
  transfer: "Transfer",
  design: "Design decision",
};

export function ItemFrame({ item, gid, status, children }: { item: Item; gid: string; status?: "correct" | "incorrect" | null; children: ReactNode }) {
  const meta = typeMeta[item.type];
  return (
    <section
      id={`item-${item.id}`}
      data-gid={gid}
      aria-label={`${meta.label}: ${skillLabel[item.skill]}`}
      className={cn(
        "not-prose my-6 scroll-mt-24 overflow-hidden rounded-xl border bg-surface shadow-card",
        status === "correct" ? "border-success/50" : status === "incorrect" ? "border-danger/40" : "border-border",
      )}
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2/60 px-4 py-2">
        <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-text">
          {meta.icon}
          {meta.label}
        </span>
        <Badge tone="neutral">{skillLabel[item.skill]}</Badge>
        {item.difficulty > 1 && <Badge tone={item.difficulty === 3 ? "violet" : "info"}>{item.difficulty === 3 ? "Challenging" : "Stretch"}</Badge>}
        {status === "correct" && (
          <span className="ml-auto inline-flex items-center gap-1 text-[12.5px] font-medium text-success">
            <CheckCircle2 className="size-4" aria-hidden /> Correct
          </span>
        )}
      </header>
      <div className="px-4 pt-3 pb-4">
        <Markdown className="text-[15px]">{item.prompt}</Markdown>
        <div className="mt-3">{children}</div>
      </div>
    </section>
  );
}

export function Verdict({ correct, feedback, explanation, extra }: { correct: boolean; feedback?: string | null; explanation: string; extra?: ReactNode }) {
  return (
    <div
      role="status"
      className={cn("mt-4 rounded-lg border px-4 py-3 text-sm", correct ? "border-success/30 bg-success-soft/70" : "border-danger/30 bg-danger-soft/70")}
    >
      <p className={cn("flex items-center gap-2 font-semibold", correct ? "text-success" : "text-danger")}>
        {correct ? <CheckCircle2 className="size-4" aria-hidden /> : <XCircle className="size-4" aria-hidden />}
        {correct ? "Correct" : "Not quite"}
      </p>
      {feedback && <Markdown className="mt-1.5 text-[14px]">{feedback}</Markdown>}
      <div className="mt-2 border-t border-current/10 pt-2">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-muted">Why</p>
        <Markdown className="mt-0.5 text-[14px]">{explanation}</Markdown>
      </div>
      {extra}
    </div>
  );
}

/** Deterministic shuffle so a learner sees a stable order for the same item. */
export function seededShuffle<T>(values: T[], seed: string): T[] {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  const out = [...values];
  for (let i = out.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
    const j = h % (i + 1);
    [out[i], out[j]] = [out[j]!, out[i]!];
  }
  return out;
}
