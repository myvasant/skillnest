// "Skip what you know": a short diagnostic built from mastery-check items.
// For each lesson concept, two items (preferring an implementation/debugging
// item plus one other skill). Both correct → concept marked mastered via diagnostic.
import { useMemo, useRef, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { curriculum, loadLesson } from "../../content/runtime";
import { itemGid } from "../../content/build";
import type { Item } from "../../content/schema";
import { recordAttempt, setDiagnostic } from "../../storage/actions";
import { progressStore } from "../../storage/store";
import { useAsync } from "../../lib/hooks";
import { Button, Card, Spinner } from "../../components/ui";
import { ItemView } from "../assessment/ItemView";

export function pickDiagnosticItems(items: Item[], masteryIds: string[]): Item[] {
  const pool = items.filter((i) => masteryIds.includes(i.id));
  const code = pool.find((i) => i.type === "code" || i.type === "debug");
  const other = pool.find((i) => i !== code && (i.type === "predict-output" || i.type === "mcq")) ?? pool.find((i) => i !== code);
  return [code, other].filter((i): i is Item => Boolean(i));
}

export function Diagnostic({ conceptIds, onDone }: { conceptIds: string[]; onDone: () => void }) {
  const targets = useMemo(() => conceptIds.filter((id) => curriculum.concepts[id]?.lessonId), [conceptIds]);
  const state = useAsync(async () => {
    const out: { conceptId: string; lessonId: string; items: Item[] }[] = [];
    for (const id of targets) {
      const lessonId = curriculum.concepts[id]!.lessonId!;
      const lesson = await loadLesson(lessonId);
      if (!lesson?.masteryCheck) continue;
      out.push({ conceptId: id, lessonId, items: pickDiagnosticItems(lesson.items, lesson.masteryCheck.items) });
    }
    return out;
  }, [targets.join(",")]);
  const [results, setResults] = useState<Record<string, Record<string, boolean>>>({});
  const resultsRef = useRef<Record<string, Record<string, boolean>>>({});

  if (state.status !== "ready") return <Spinner label="Preparing diagnostic" />;
  const groups = state.value;
  if (!groups.length) return <p className="text-[14px] text-muted">There are no assessable lessons left to test out of on this path.</p>;

  const answer = (conceptId: string, gid: string, total: number) => (correct: boolean) => {
    const forConcept = { ...(resultsRef.current[conceptId] ?? {}) };
    if (gid in forConcept) return;
    forConcept[gid] = correct;
    resultsRef.current = { ...resultsRef.current, [conceptId]: forConcept };
    setResults(resultsRef.current);
    progressStore.update((p, now) => recordAttempt(p, { gid, correct, context: "diagnostic" }, now));
    const answers = Object.values(forConcept);
    if (answers.length === total && answers.every(Boolean)) {
      progressStore.update((p, now) => setDiagnostic(p, conceptId, "passed", now));
    }
  };

  const finished = groups.every((g) => Object.keys(results[g.conceptId] ?? {}).length === g.items.length);

  return (
    <div className="space-y-8">
      {groups.map((g) => {
        const r = results[g.conceptId] ?? {};
        const complete = Object.keys(r).length === g.items.length;
        const passed = complete && Object.values(r).every(Boolean);
        return (
          <section key={g.conceptId} aria-labelledby={`diag-${g.conceptId}`}>
            <h3 id={`diag-${g.conceptId}`} className="flex items-center gap-2 text-[16px] font-semibold">
              {curriculum.concepts[g.conceptId]!.title}
              {complete &&
                (passed ? (
                  <CheckCircle2 className="size-4 text-success" aria-label="passed" />
                ) : (
                  <XCircle className="size-4 text-danger" aria-label="not passed" />
                ))}
            </h3>
            {complete && (
              <p className="text-[13.5px] text-muted">
                {passed
                  ? "Marked as mastered (diagnostic). It will appear in your spaced reviews."
                  : "Not skipped — this lesson stays on your path. That's useful information, not a failure."}
              </p>
            )}
            {g.items.map((item) => {
              const gid = itemGid(g.lessonId, item.id);
              return <ItemView key={gid} item={item} gid={gid} mode="assessment" onAnswered={answer(g.conceptId, gid, g.items.length)} />;
            })}
          </section>
        );
      })}
      {finished && (
        <Card className="p-5">
          <p className="font-semibold">Diagnostic complete</p>
          <p className="mt-1 text-[14px] text-muted">Your recommendations now skip what you demonstrated and start at your first gap.</p>
          <Button className="mt-3" variant="primary" onClick={onDone}>
            Back to the path
          </Button>
        </Card>
      )}
    </div>
  );
}
