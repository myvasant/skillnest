import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { CalendarClock, Eye, MessagesSquare } from "lucide-react";
import { curriculum, loadInterview } from "../../content/runtime";
import type { InterviewQuestion } from "../../content/schema";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, EmptyState, PageHeader, Spinner, cn } from "../../components/ui";
import { useAsync, useDocumentTitle } from "../../lib/hooks";
import { daysUntil } from "../../engine/review";
import { rateInterviewQuestion } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";

type Q = InterviewQuestion & { category: string };

const kindLabel: Record<Q["kind"], string> = {
  conceptual: "Conceptual",
  coding: "Coding",
  debugging: "Debugging",
  design: "System / design",
  scenario: "Scenario",
  sql: "SQL",
};

function QuestionCard({ q, defaultOpen }: { q: Q; defaultOpen?: boolean }) {
  const progress = useProgress();
  const [revealed, setRevealed] = useState(Boolean(defaultOpen));
  const state = progress.interview[q.id];
  const due = state ? daysUntil(state.dueAt, new Date()) : null;
  return (
    <Card id={`q-${q.id}`} className="scroll-mt-24 p-5">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge tone={q.level === "junior" ? "success" : q.level === "mid" ? "info" : "violet"}>{q.level}</Badge>
        <Badge tone="neutral">{kindLabel[q.kind]}</Badge>
        {q.concepts.slice(0, 3).map((c) => (
          <Link key={c} to={`/concept/${c}`} className="text-[12px] text-muted hover:text-accent">
            #{curriculum.concepts[c]?.title ?? c}
          </Link>
        ))}
        {state && (
          <span className="ml-auto flex items-center gap-1 text-[12px] text-muted">
            <CalendarClock className="size-3.5" aria-hidden />
            last: {state.rating} · {due !== null && due <= 0 ? "due now" : `revise in ${due}d`}
          </span>
        )}
      </div>
      <Markdown className="text-[15.5px] font-medium">{q.question}</Markdown>
      {!revealed ? (
        <div className="mt-3 flex items-center gap-3">
          <Button size="sm" onClick={() => setRevealed(true)} icon={<Eye className="size-3.5" aria-hidden />}>
            Reveal model answer
          </Button>
          <span className="text-[12.5px] text-muted">Answer out loud or in writing first — interviews test recall, not recognition.</span>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-surface-2/60 p-4">
            <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted">Model answer</p>
            <Markdown className="text-[14.5px]">{q.answer}</Markdown>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted">A strong answer covers</p>
              <ul className="list-disc space-y-1 pl-5 text-[14px]">
                {q.keyPoints.map((k) => (
                  <li key={k}>
                    <Markdown inline className="text-[14px]">
                      {k}
                    </Markdown>
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-3">
              {q.pitfalls.length > 0 && (
                <div>
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted">Pitfalls</p>
                  <ul className="list-disc space-y-1 pl-5 text-[14px]">
                    {q.pitfalls.map((k) => (
                      <li key={k}>
                        <Markdown inline className="text-[14px]">
                          {k}
                        </Markdown>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {q.followUps.length > 0 && (
                <div>
                  <p className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-muted">Likely follow-ups</p>
                  <ul className="list-disc space-y-1 pl-5 text-[14px]">
                    {q.followUps.map((k) => (
                      <li key={k}>
                        <Markdown inline className="text-[14px]">
                          {k}
                        </Markdown>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <span className="text-[13px] text-muted">How did you do?</span>
            {(
              [
                ["missed", "Missed it", "danger"],
                ["partial", "Partly", "secondary"],
                ["solid", "Nailed it", "primary"],
              ] as const
            ).map(([rating, label, variant]) => (
              <Button
                key={rating}
                size="sm"
                variant={state?.rating === rating ? variant : "secondary"}
                onClick={() => progressStore.update((p, now) => rateInterviewQuestion(p, q.id, rating, now))}
              >
                {label}
              </Button>
            ))}
            <span className="text-[12px] text-faint">Schedules revision: 1 day · 3 days · 7+ days</span>
          </div>
        </div>
      )}
    </Card>
  );
}

export function InterviewPage() {
  useDocumentTitle("Interview prep");
  const [params, setParams] = useSearchParams();
  const progress = useProgress();
  const state = useAsync(() => loadInterview(), []);
  const category = params.get("category") ?? "";
  const level = params.get("level") ?? "";
  const kind = params.get("kind") ?? "";
  const concept = params.get("concept") ?? "";
  const single = params.get("q") ?? "";
  const dueOnly = params.get("due") === "1";

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("q");
    setParams(next, { replace: true });
  };

  const questions = useMemo(() => {
    if (state.status !== "ready") return [] as Q[];
    const now = new Date();
    return Object.values(state.value).filter((q) => {
      if (single) return q.id === single;
      if (category && q.category !== category) return false;
      if (level && q.level !== level) return false;
      if (kind && q.kind !== kind) return false;
      if (concept && !q.concepts.includes(concept)) return false;
      if (dueOnly) {
        const s = progress.interview[q.id];
        if (!s || new Date(s.dueAt) > now) return false;
      }
      return true;
    });
  }, [state, category, level, kind, concept, single, dueOnly, progress.interview]);

  const dueCount = Object.values(progress.interview).filter((s) => new Date(s.dueAt) <= new Date()).length;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Interview preparation"
        description="Questions graded by level, with model answers, the points a strong answer covers, common pitfalls and follow-ups. Rate yourself to schedule revision."
      />
      <div className="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="Categories">
        <button
          role="tab"
          aria-selected={!category}
          onClick={() => set("category", "")}
          className={cn("rounded-full border px-3 py-1 text-[13px]", !category ? "border-accent bg-accent-soft text-accent" : "border-border text-muted")}
        >
          All
        </button>
        {curriculum.interviewCategories.map((c) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={category === c.id}
            onClick={() => set("category", c.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-[13px]",
              category === c.id ? "border-accent bg-accent-soft text-accent" : "border-border text-muted",
            )}
          >
            {c.title} <span className="text-faint">{c.questionIds.length}</span>
          </button>
        ))}
      </div>
      <Card className="mb-6 flex flex-wrap items-center gap-4 px-4 py-3 text-[13px]">
        <label className="flex items-center gap-2 text-muted">
          Level
          <select value={level} onChange={(e) => set("level", e.target.value)} className="h-8 rounded-md border border-border bg-surface px-2 text-text">
            <option value="">All</option>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-muted">
          Type
          <select value={kind} onChange={(e) => set("kind", e.target.value)} className="h-8 rounded-md border border-border bg-surface px-2 text-text">
            <option value="">All</option>
            {Object.entries(kindLabel).map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-muted">
          <input type="checkbox" checked={dueOnly} onChange={(e) => set("due", e.target.checked ? "1" : "")} className="accent-[var(--gw-accent)]" />
          Due for revision ({dueCount})
        </label>
        {(concept || single) && (
          <button className="ml-auto text-accent underline" onClick={() => setParams({}, { replace: true })}>
            Clear {concept ? `concept: ${curriculum.concepts[concept]?.title}` : "selection"}
          </button>
        )}
      </Card>
      {state.status === "loading" && <Spinner label="Loading questions" />}
      {state.status === "ready" && questions.length === 0 && (
        <EmptyState icon={<MessagesSquare className="size-8" />} title="No questions match these filters." />
      )}
      <div className="space-y-4">
        {questions.map((q) => (
          <QuestionCard key={q.id} q={q} defaultOpen={Boolean(single)} />
        ))}
      </div>
    </div>
  );
}
