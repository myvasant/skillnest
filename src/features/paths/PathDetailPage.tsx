import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { CheckCircle2, FastForward } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { activePathId } from "../../engine/recommend";
import { isSatisfied } from "../../engine/mastery";
import { useDocumentTitle, useMastery } from "../../lib/hooks";
import { setDiagnostic, updateSettings } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";
import { Badge, Button, ButtonLink, Card, EmptyState, PageHeader, ProgressBar, levelTone } from "../../components/ui";
import { StatusIcon, statusLabel } from "../curriculum/status";
import { Diagnostic } from "./Diagnostic";

export function PathDetailPage() {
  const { pathId = "" } = useParams();
  const path = curriculum.paths.find((p) => p.id === pathId);
  const progress = useProgress();
  const mastery = useMastery();
  const [diagnosing, setDiagnosing] = useState(false);
  useDocumentTitle(path?.title ?? "Path");

  const byStage = useMemo(() => {
    if (!path) return [];
    return curriculum.stages
      .map((s) => ({ stage: s, ids: path.conceptIds.filter((id) => curriculum.concepts[id]!.stage === s.id) }))
      .filter((g) => g.ids.length);
  }, [path]);

  if (!path) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <EmptyState title="Path not found" action={<ButtonLink to="/paths">All paths</ButtonLink>} />
      </div>
    );
  }

  const isActive = activePathId(curriculum, progress) === path.id;
  const unmasteredLessonConcepts = path.conceptIds.filter((id) => curriculum.concepts[id]!.lessonId && !isSatisfied(mastery[id]!));
  const done = path.conceptIds.filter((id) => isSatisfied(mastery[id]!)).length;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow={
          <Link to="/paths" className="hover:text-text">
            ← Learning paths
          </Link>
        }
        title={path.title}
        description={path.summary}
        actions={
          <>
            {!isActive && (
              <Button
                variant="primary"
                onClick={() => progressStore.update((s, now) => updateSettings(s, { activePath: path.id }, now))}
                icon={<CheckCircle2 className="size-4" aria-hidden />}
              >
                Make this my path
              </Button>
            )}
            {unmasteredLessonConcepts.length > 0 && !diagnosing && (
              <Button onClick={() => setDiagnosing(true)} icon={<FastForward className="size-4" aria-hidden />}>
                Skip what you know
              </Button>
            )}
          </>
        }
      />
      <Card className="mb-6 p-5">
        <p className="text-[14px] font-medium">You will be able to:</p>
        <ul className="mt-2 grid gap-1.5 text-[14px] text-muted md:grid-cols-2">
          {path.outcomes.map((o) => (
            <li key={o} className="flex gap-2">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
              {o}
            </li>
          ))}
        </ul>
        <ProgressBar className="mt-4" value={done / path.conceptIds.length} label="Path progress" tone="success" />
        <p className="mt-1.5 text-[12.5px] text-muted">
          {done} of {path.conceptIds.length} concepts done. Order follows prerequisites: everything above a concept is something it builds on.
        </p>
      </Card>

      {diagnosing && (
        <Card className="mb-8 p-5">
          <h2 className="text-lg font-semibold">Diagnostic: skip what you already know</h2>
          <p className="mb-4 mt-1 text-[14px] text-muted">
            Two questions per lesson, taken from its mastery check — one of them always asks you to write or fix code. Answer both correctly to skip that
            lesson. No hints, one attempt each.
          </p>
          <Diagnostic conceptIds={unmasteredLessonConcepts} onDone={() => setDiagnosing(false)} />
        </Card>
      )}

      <div className="space-y-8">
        {byStage.map(({ stage, ids }) => (
          <section key={stage.id} aria-labelledby={`ps-${stage.id}`}>
            <h2 id={`ps-${stage.id}`} className="mb-2 text-[15px] font-semibold">
              Stage {stage.order}: {stage.title} <span className="font-normal text-muted">· {ids.length}</span>
            </h2>
            <Card>
              <ol className="divide-y divide-border">
                {ids.map((id) => {
                  const c = curriculum.concepts[id]!;
                  const m = mastery[id]!;
                  const isTarget = path.targets.includes(id);
                  return (
                    <li key={id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                      <StatusIcon status={m.status} className="size-4" />
                      <div className="min-w-0 flex-1">
                        <Link to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`} className="font-medium hover:text-accent">
                          {c.title}
                        </Link>
                        {isTarget && (
                          <Badge tone="violet" className="ml-2">
                            Goal
                          </Badge>
                        )}
                      </div>
                      <Badge tone={levelTone(c.level)}>{c.level}</Badge>
                      {c.lessonId ? <Badge tone="accent">Lesson</Badge> : <Badge tone="neutral">Outline</Badge>}
                      <span className="w-36 text-right text-[12px] text-muted">{statusLabel(m)}</span>
                      {!c.lessonId && m.status !== "mastered" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => progressStore.update((p, now) => setDiagnostic(p, id, "self-reported", now))}
                          title="Mark as known (self-reported)"
                        >
                          I know this
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ol>
            </Card>
          </section>
        ))}
      </div>
    </div>
  );
}
