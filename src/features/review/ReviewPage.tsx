import { useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { CalendarClock, CheckCircle2, Repeat, XCircle } from "lucide-react";
import { curriculum, loadLesson } from "../../content/runtime";
import { itemGid } from "../../content/build";
import type { Item } from "../../content/schema";
import { daysUntil, intervalForBox } from "../../engine/review";
import { completeReview, recordAttempt } from "../../storage/actions";
import type { Progress } from "../../storage/progress";
import { progressStore, useProgress } from "../../storage/store";
import { useAsync, useDocumentTitle, useMastery } from "../../lib/hooks";
import { Badge, ButtonLink, Card, EmptyState, PageHeader, Spinner } from "../../components/ui";
import { ItemView } from "../assessment/ItemView";

export const REVIEW_SIZE = 3;
export const REVIEW_PASS = 2 / 3;

/**
 * Pick review items: least recently answered first, varying the skill, and
 * including a coding item once the concept has been reviewed successfully before.
 */
export function pickReviewItems(items: Item[], lessonId: string, progress: Progress, box: number): Item[] {
  const lastAt = (i: Item) => progress.items[itemGid(lessonId, i.id)]?.lastAt ?? "";
  const pool = items.filter((i) => i.type !== "explain").sort((a, b) => lastAt(a).localeCompare(lastAt(b)) || a.id.localeCompare(b.id));
  const chosen: Item[] = [];
  if (box >= 2) {
    const code = pool.find((i) => i.type === "code" || i.type === "debug");
    if (code) chosen.push(code);
  }
  for (const item of pool) {
    if (chosen.length >= REVIEW_SIZE) break;
    if (chosen.includes(item)) continue;
    if (chosen.some((c) => c.skill === item.skill) && pool.some((p) => !chosen.includes(p) && !chosen.some((c) => c.skill === p.skill))) continue;
    chosen.push(item);
  }
  for (const item of pool) {
    if (chosen.length >= REVIEW_SIZE) break;
    if (!chosen.includes(item)) chosen.push(item);
  }
  return chosen;
}

function ReviewSession({ conceptId }: { conceptId: string }) {
  const concept = curriculum.concepts[conceptId];
  const [session] = useState(() => {
    const p = progressStore.get();
    return { box: p.concepts[conceptId]?.review?.box ?? 1, snapshot: p };
  });
  const state = useAsync(() => (concept?.lessonId ? loadLesson(concept.lessonId) : Promise.resolve(null)), [conceptId]);
  const items = useMemo(
    () => (state.status === "ready" && state.value ? pickReviewItems(state.value.items, state.value.id, session.snapshot, session.box) : []),
    [state, session],
  );
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const answersRef = useRef<Record<string, boolean>>({});
  const [result, setResult] = useState<{ passed: boolean; correct: number } | null>(null);

  if (!concept?.lessonId) return <EmptyState title="Nothing to review for this concept." />;
  if (state.status !== "ready" || !state.value) return <Spinner label="Preparing review" />;
  const lessonId = state.value.id;

  const onAnswered = (gid: string) => (correct: boolean) => {
    if (gid in answersRef.current) return;
    answersRef.current = { ...answersRef.current, [gid]: correct };
    setAnswers(answersRef.current);
    progressStore.update((p, now) => recordAttempt(p, { gid, correct, context: "review" }, now));
    const values = Object.values(answersRef.current);
    if (values.length === items.length) {
      const correctCount = values.filter(Boolean).length;
      const passed = correctCount / items.length >= REVIEW_PASS;
      setResult({ passed, correct: correctCount });
      progressStore.update((p, now) => completeReview(p, conceptId, passed, now));
    }
  };

  const review = progressStore.get().concepts[conceptId]?.review;
  return (
    <div>
      <h2 className="mb-1 text-xl font-semibold">{concept.title}</h2>
      <p className="mb-4 text-[14px] text-muted">
        {items.length} questions, chosen from ones you haven't seen recently. Pass with {Math.ceil(REVIEW_PASS * items.length)} correct to push the next review
        further out
        {` (currently box ${session.box} → next interval ${intervalForBox(session.box + 1)} days).`}
      </p>
      {items.map((item) => {
        const gid = itemGid(lessonId, item.id);
        return <ItemView key={gid} item={item} gid={gid} mode="assessment" onAnswered={onAnswered(gid)} />;
      })}
      <p className="text-[13px] text-muted" aria-live="polite">
        Answered {Object.keys(answers).length} of {items.length}
      </p>
      {result && (
        <Card className="mt-4 p-5" role="status">
          <p className={`flex items-center gap-2 text-lg font-semibold ${result.passed ? "text-success" : "text-warning"}`}>
            {result.passed ? <CheckCircle2 className="size-5" aria-hidden /> : <XCircle className="size-5" aria-hidden />}
            {result.passed ? "Review passed" : "Needs another look"}
          </p>
          <p className="mt-1 text-[14px]">
            {result.correct} of {items.length} correct.{" "}
            {result.passed && review
              ? `Next review in ${Math.max(0, daysUntil(review.dueAt, new Date()))} days.`
              : "This concept is due again now. Revisit the lesson's explanations and practice, then review again."}
          </p>
          <div className="mt-3 flex gap-2">
            <ButtonLink to="/review" variant="primary">
              Back to reviews
            </ButtonLink>
            {!result.passed && <ButtonLink to={`/learn/${lessonId}`}>Open the lesson</ButtonLink>}
          </div>
        </Card>
      )}
    </div>
  );
}

export function ReviewPage() {
  useDocumentTitle("Review");
  const [params] = useSearchParams();
  const conceptId = params.get("concept");
  const mastery = useMastery();
  useProgress();
  const scheduled = Object.values(mastery)
    .filter((m) => m.reviewDueAt)
    .sort((a, b) => a.reviewDueAt!.localeCompare(b.reviewDueAt!));
  const due = scheduled.filter((m) => m.reviewDue);
  const upcoming = scheduled.filter((m) => !m.reviewDue);
  const now = new Date();

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Spaced review"
        description="Concepts come back for a short review after 1, 3, 7, 16, 35 and 90 days. Each success pushes the next review further out; a miss brings it back immediately. This schedule is simple and fully visible — no hidden algorithm."
      />
      {conceptId ? (
        <ReviewSession key={conceptId} conceptId={conceptId} />
      ) : (
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold">
              <Repeat className="size-4 text-accent" aria-hidden /> Due now ({due.length})
            </h2>
            {due.length === 0 ? (
              <p className="text-[14px] text-muted">
                Nothing is due.{" "}
                {scheduled.length === 0 ? "Pass a lesson's mastery check to start your review schedule." : "Come back when the next review is due."}
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {due.map((m) => (
                  <li key={m.conceptId} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="font-medium">{curriculum.concepts[m.conceptId]?.title}</span>
                    <ButtonLink to={`/review?concept=${m.conceptId}`} size="sm" variant="primary">
                      Review
                    </ButtonLink>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="p-5">
            <h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold">
              <CalendarClock className="size-4 text-muted" aria-hidden /> Upcoming
            </h2>
            {upcoming.length === 0 ? (
              <p className="text-[14px] text-muted">No upcoming reviews.</p>
            ) : (
              <ul className="divide-y divide-border text-[14px]">
                {upcoming.map((m) => {
                  const d = daysUntil(m.reviewDueAt!, now);
                  const box = progressStore.get().concepts[m.conceptId]?.review?.box ?? 1;
                  return (
                    <li key={m.conceptId} className="flex items-center justify-between gap-3 py-2.5">
                      <Link to={`/concept/${m.conceptId}`} className="hover:text-accent">
                        {curriculum.concepts[m.conceptId]?.title}
                      </Link>
                      <span className="flex items-center gap-2 text-muted">
                        <Badge tone="neutral">box {box}</Badge>
                        in {d} day{d === 1 ? "" : "s"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
