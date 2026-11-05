// The end-of-lesson mastery check: unseen items across several skills, one
// attempt each, no hints. Passing marks the concept mastered and schedules
// the first spaced review.
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Award, CheckCircle2, Flag, RotateCcw, XCircle } from "lucide-react";
import type { Lesson } from "../../content/schema";
import { itemGid } from "../../content/build";
import { curriculum } from "../../content/runtime";
import { scoreMasteryCheck, type MasteryCheckResult } from "../../engine/mastery";
import { recommend } from "../../engine/recommend";
import { daysUntil } from "../../engine/review";
import { completeMasteryCheck, recordAttempt } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";
import { Badge, Button, ButtonLink, Card, cn } from "../../components/ui";
import { ItemView } from "../assessment/ItemView";
import { skillLabel } from "../assessment/shared";

type Phase = "intro" | "running" | "done";

export function MasteryCheck({ lesson }: { lesson: Lesson }) {
  const progress = useProgress();
  const meta = curriculum.lessons[lesson.id]!;
  const concept = progress.concepts[lesson.concept];
  const [phase, setPhase] = useState<Phase>("intro");
  const [round, setRound] = useState(0);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const answersRef = useRef<Record<string, boolean>>({});
  const [outcome, setOutcome] = useState<MasteryCheckResult | null>(null);
  const items = useMemo(() => (lesson.masteryCheck?.items ?? []).map((id) => lesson.items.find((i) => i.id === id)!).filter(Boolean), [lesson]);

  if (!lesson.masteryCheck) return null;
  const threshold = lesson.masteryCheck.passThreshold;
  const answeredCount = Object.keys(answers).length;
  const reviewDue = concept?.review ? daysUntil(concept.review.dueAt, new Date()) : null;

  const onAnswered = (gid: string) => (correct: boolean) => {
    if (gid in answersRef.current) return;
    const next = { ...answersRef.current, [gid]: correct };
    answersRef.current = next;
    setAnswers(next);
    progressStore.update((p, now) => recordAttempt(p, { gid, correct, context: "mastery" }, now));
    if (Object.keys(next).length === items.length) {
      const result = scoreMasteryCheck(
        Object.entries(next).map(([g, c]) => ({ gid: g, correct: c })),
        curriculum,
        threshold,
      );
      setOutcome(result);
      setPhase("done");
      progressStore.update((p, now) =>
        completeMasteryCheck(p, { conceptId: lesson.concept, lessonId: lesson.id, score: result.score, passed: result.passed }, now),
      );
    }
  };

  const start = () => {
    answersRef.current = {};
    setAnswers({});
    setOutcome(null);
    setRound((r) => r + 1);
    setPhase("running");
  };

  const next = outcome?.passed ? recommend(curriculum, progressStore.get(), new Date()).primary : null;

  return (
    <section id="mastery-check" className="scroll-mt-24" aria-labelledby="mastery-heading">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-accent-soft/40 px-5 py-4">
          <div>
            <h2 id="mastery-heading" className="flex items-center gap-2 text-lg font-semibold">
              <Award className="size-5 text-accent" aria-hidden /> Mastery check
            </h2>
            <p className="mt-0.5 text-[13.5px] text-muted">
              {items.length} questions · one attempt each · no hints · pass mark {Math.round(threshold * 100)}%
              {items.some((i) => i.type === "code" || i.type === "debug") && " · includes independent coding"}
            </p>
          </div>
          {concept?.masteredAt && (
            <Badge tone="success">
              <CheckCircle2 className="size-3.5" aria-hidden /> Mastered {new Date(concept.masteredAt).toLocaleDateString()}
            </Badge>
          )}
        </div>
        <div className="px-5 py-4">
          {phase === "intro" && (
            <div className="space-y-3 text-[14.5px]">
              <p>
                Opening a lesson isn't proof of learning. This check uses <strong>new</strong> questions to confirm you can recognise, predict, write and debug
                this concept on your own. It covers: {[...new Set(items.map((i) => skillLabel[i.skill].toLowerCase()))].join(", ")}.
              </p>
              {concept?.masteredAt && reviewDue !== null && (
                <p className="text-muted">
                  Next spaced review: {reviewDue <= 0 ? "due now" : `in ${reviewDue} day${reviewDue === 1 ? "" : "s"}`}.{" "}
                  {reviewDue <= 0 && (
                    <Link className="text-accent underline" to={`/review?concept=${lesson.concept}`}>
                      Start review
                    </Link>
                  )}
                </p>
              )}
              {concept && concept.masteryScore !== null && !concept.masteredAt && (
                <p className="text-muted">Last attempt: {Math.round(concept.masteryScore * 100)}%. Revisit the practice items, then try again.</p>
              )}
              <Button variant="primary" onClick={start} icon={<Flag className="size-4" aria-hidden />}>
                {concept?.lastMasteryAttemptAt ? "Take the check again" : "Start mastery check"}
              </Button>
            </div>
          )}
          {phase !== "intro" && (
            <div>
              <div className="mb-2 flex items-center justify-between text-[13px] text-muted">
                <span>
                  Answered {answeredCount} of {items.length}
                </span>
              </div>
              <div className="flex gap-1" aria-hidden>
                {items.map((item) => {
                  const gid = itemGid(lesson.id, item.id);
                  return (
                    <span
                      key={item.id}
                      className={cn("h-1.5 flex-1 rounded-full", gid in answers ? (answers[gid] ? "bg-success" : "bg-danger") : "bg-surface-3")}
                    />
                  );
                })}
              </div>
              <div key={round}>
                {items.map((item) => (
                  <ItemView
                    key={item.id}
                    item={item}
                    gid={itemGid(lesson.id, item.id)}
                    mode="assessment"
                    onAnswered={onAnswered(itemGid(lesson.id, item.id))}
                  />
                ))}
              </div>
            </div>
          )}
          {phase === "done" && outcome && (
            <div
              className={cn("mt-2 rounded-xl border p-5", outcome.passed ? "border-success/40 bg-success-soft/60" : "border-warning/40 bg-warning-soft/60")}
              role="status"
            >
              <p className={cn("flex items-center gap-2 text-lg font-semibold", outcome.passed ? "text-success" : "text-warning")}>
                {outcome.passed ? <Award className="size-5" aria-hidden /> : <XCircle className="size-5" aria-hidden />}
                {outcome.passed ? `${meta.title}: mastered` : "Not mastered yet"}
              </p>
              <p className="mt-1 text-[14.5px]">{outcome.reason}</p>
              {outcome.passed ? (
                <p className="mt-2 text-[14px] text-muted">
                  Your first spaced review is scheduled for tomorrow. Reviews get further apart each time you succeed.
                </p>
              ) : (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-[14px]">
                  {items
                    .filter((i) => answers[itemGid(lesson.id, i.id)] === false)
                    .map((i) => (
                      <li key={i.id}>
                        Missed a <strong>{skillLabel[i.skill].toLowerCase()}</strong> question — read its explanation above, then redo the practice items for
                        that skill.
                      </li>
                    ))}
                </ul>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                {outcome.passed && next && (
                  <ButtonLink to={next.url} variant="primary">
                    {next.title}
                  </ButtonLink>
                )}
                <Button onClick={start} icon={<RotateCcw className="size-4" aria-hidden />}>
                  {outcome.passed ? "Retake for practice" : "Try again"}
                </Button>
              </div>
              {outcome.passed && next && <p className="mt-2 text-[13px] text-muted">Why this next: {next.reason}</p>}
            </div>
          )}
        </div>
      </Card>
    </section>
  );
}
