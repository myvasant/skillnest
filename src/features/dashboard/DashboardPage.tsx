import { useMemo, type ReactNode } from "react";
import { Link } from "react-router";
import {
  ArrowRight,
  Award,
  CalendarClock,
  CircleAlert,
  Compass,
  Flame,
  Hammer,
  History,
  PlayCircle,
  Repeat,
  Route,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { curriculum } from "../../content/runtime";
import { daysUntil } from "../../engine/review";
import type { RecommendationKind } from "../../engine/recommend";
import { useDocumentTitle, useMastery, useRecommendations } from "../../lib/hooks";
import { useProgress } from "../../storage/store";
import { Badge, ButtonLink, Card, EmptyState, ProgressBar, SectionHeading, cn } from "../../components/ui";
import { StatusIcon, statusLabel } from "../curriculum/status";

const kindIcon: Record<RecommendationKind, typeof PlayCircle> = {
  review: Repeat,
  weak: TriangleAlert,
  continue: PlayCircle,
  "mastery-check": Award,
  next: Sparkles,
  prerequisite: CircleAlert,
  done: Compass,
};

const kindLabel: Record<RecommendationKind, string> = {
  review: "Spaced review due",
  weak: "Needs attention",
  continue: "Continue learning",
  "mastery-check": "Ready for mastery check",
  next: "Recommended next",
  prerequisite: "Prerequisite first",
  done: "Path complete",
};

export function DashboardPage() {
  useDocumentTitle("Dashboard");
  const progress = useProgress();
  const mastery = useMastery();
  const recs = useRecommendations();
  const path = curriculum.paths.find((p) => p.id === recs.pathId)!;
  const now = new Date();
  const isNew = Object.keys(progress.lessons).length === 0 && progress.history.length === 0;

  const pathStats = useMemo(() => {
    const withLessons = path.conceptIds.filter((id) => curriculum.concepts[id]?.lessonId);
    const mastered = withLessons.filter((id) => mastery[id]?.status === "mastered").length;
    const proficient = withLessons.filter((id) => mastery[id]?.status === "proficient").length;
    return { total: path.conceptIds.length, withLessons: withLessons.length, mastered, proficient };
  }, [path, mastery]);

  const reviews = useMemo(
    () =>
      Object.values(mastery)
        .filter((m) => m.reviewDueAt)
        .sort((a, b) => a.reviewDueAt!.localeCompare(b.reviewDueAt!))
        .slice(0, 6),
    [mastery],
  );
  const weak = Object.values(mastery).filter((m) => m.weak);
  const mastered = Object.values(mastery).filter((m) => m.status === "mastered");

  const week = useMemo(() => {
    const since = now.getTime() - 7 * 24 * 3600 * 1000;
    const recent = progress.history.filter((h) => new Date(h.at).getTime() >= since);
    const days = new Set(recent.map((h) => h.at.slice(0, 10)));
    return { answered: recent.length, correct: recent.filter((h) => h.correct).length, activeDays: days.size };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress.history]);

  const recentLessons = Object.entries(progress.lessons)
    .sort(([, a], [, b]) => b.lastVisitedAt.localeCompare(a.lastVisitedAt))
    .slice(0, 4);

  const activeProjects = Object.entries(progress.projects).filter(([id]) => curriculum.projects.some((p) => p.id === id));
  const PrimaryIcon = kindIcon[recs.primary.kind];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-8">
        <p className="text-[13px] text-muted">{now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-[28px]">{isNew ? "Welcome to Groundwork" : "Welcome back"}</h1>
      </header>

      {isNew && (
        <Card className="mb-6 overflow-hidden">
          <div className="grid gap-6 p-6 md:grid-cols-[1.4fr_1fr]">
            <div>
              <h2 className="text-lg font-semibold">How learning works here</h2>
              <ol className="mt-3 space-y-2 text-[14.5px] text-text">
                <li>
                  <strong>Understand</strong> — each lesson explains what, why, and how it works inside, with visual step-throughs.
                </li>
                <li>
                  <strong>Practise</strong> — predict outputs, write and debug real Python that runs right in your browser.
                </li>
                <li>
                  <strong>Prove it</strong> — a mastery check with fresh questions decides when a concept is mastered.
                </li>
                <li>
                  <strong>Remember</strong> — spaced reviews bring concepts back just as you start to forget them.
                </li>
              </ol>
              <p className="mt-3 text-[13.5px] text-muted">Everything runs locally. No account, no tracking, no cost.</p>
            </div>
            <div className="flex flex-col justify-center gap-3 rounded-xl bg-surface-2 p-5">
              <p className="text-[13px] font-medium text-muted">Your path: {path.title}</p>
              <ButtonLink to={recs.primary.url} variant="primary" icon={<PlayCircle className="size-4" aria-hidden />}>
                Start: {recs.primary.title.replace(/^Next: /, "")}
              </ButtonLink>
              <Link to="/paths" className="text-[13px] text-accent underline underline-offset-2">
                Choose a different goal, or skip what you already know →
              </Link>
            </div>
          </div>
        </Card>
      )}

      {!isNew && (
        <Card className="mb-6 overflow-hidden">
          <div className="flex flex-col gap-5 p-6 md:flex-row md:items-center">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <PrimaryIcon className="size-6" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-accent">{kindLabel[recs.primary.kind]}</p>
              <h2 className="mt-0.5 text-xl font-semibold tracking-tight">
                {recs.primary.title.replace(/^(Next|Continue|Review|Strengthen|Prerequisite|Mastery check): /, "")}
              </h2>
              <p className="mt-1 text-[14px] text-muted">
                <span className="font-medium text-text">Why: </span>
                {recs.primary.reason}
              </p>
            </div>
            <ButtonLink to={recs.primary.url} variant="primary" icon={<ArrowRight className="size-4" aria-hidden />} className="shrink-0">
              {recs.primary.kind === "review" ? "Start review" : recs.primary.kind === "done" ? "Explore paths" : "Go"}
            </ButtonLink>
          </div>
          {progress.lastLocation && recs.primary.kind !== "continue" && (
            <div className="border-t border-border bg-surface-2/60 px-6 py-2.5 text-[13.5px]">
              <History className="mr-1.5 inline size-4 text-muted" aria-hidden />
              Last visited:{" "}
              <Link to={progress.lastLocation.path} className="font-medium text-accent underline underline-offset-2">
                {progress.lastLocation.title}
              </Link>
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="p-5">
            <SectionHeading
              title="Current learning path"
              description={path.role}
              action={
                <Link to={`/paths/${path.id}`} className="text-[13px] text-accent underline underline-offset-2">
                  View path
                </Link>
              }
            />
            <div className="flex items-center gap-2">
              <Route className="size-4 text-muted" aria-hidden />
              <span className="font-medium">{path.title}</span>
            </div>
            <ProgressBar className="mt-3" value={pathStats.withLessons ? pathStats.mastered / pathStats.withLessons : 0} label="Path mastery" tone="success" />
            <p className="mt-2 text-[13px] text-muted">
              {pathStats.mastered} of {pathStats.withLessons} available lessons mastered{pathStats.proficient ? `, ${pathStats.proficient} proficient` : ""} ·{" "}
              {pathStats.total} concepts on the full roadmap ({pathStats.total - pathStats.withLessons} still outline-only)
            </p>
            {recs.others.length > 0 && (
              <ul className="mt-4 divide-y divide-border border-t border-border">
                {recs.others.map((r) => {
                  const Icon = kindIcon[r.kind];
                  return (
                    <li key={r.url + r.kind} className="flex items-start gap-3 py-3">
                      <Icon className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <Link to={r.url} className="font-medium hover:text-accent">
                          {r.title}
                        </Link>
                        <p className="text-[13px] text-muted">{r.reason}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {recs.gaps.length > 0 && (
            <Card className="p-5">
              <SectionHeading title="Prerequisites needing attention" description="Concepts your current work builds on that you haven't mastered yet." />
              <ul className="space-y-2.5">
                {recs.gaps.map((g) => {
                  const c = curriculum.concepts[g.conceptId]!;
                  return (
                    <li key={g.conceptId} className="flex items-start gap-3 text-[14px]">
                      <CircleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                      <div>
                        <Link to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${c.id}`} className="font-medium hover:text-accent">
                          {c.title}
                        </Link>
                        <p className="text-[13px] text-muted">
                          Needed by {curriculum.concepts[g.neededBy]?.title}.{" "}
                          {g.hasLesson ? "Has a full lesson." : "Outline only for now — read the summary and key ideas."}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}

          <Card className="p-5">
            <SectionHeading title="Recent progress" description="Last 7 days" />
            <div className="grid grid-cols-3 gap-3">
              <Stat icon={<Flame className="size-4" aria-hidden />} value={week.activeDays} label="active days" />
              <Stat icon={<History className="size-4" aria-hidden />} value={week.answered} label="answers" />
              <Stat
                icon={<Award className="size-4" aria-hidden />}
                value={week.answered ? `${Math.round((week.correct / week.answered) * 100)}%` : "—"}
                label="correct"
              />
            </div>
            {recentLessons.length > 0 ? (
              <ul className="mt-4 divide-y divide-border border-t border-border">
                {recentLessons.map(([lessonId, state]) => {
                  const meta = curriculum.lessons[lessonId];
                  if (!meta) return null;
                  const m = mastery[meta.concept]!;
                  return (
                    <li key={lessonId} className="flex items-center gap-3 py-2.5 text-[14px]">
                      <StatusIcon status={m.status} className="size-4" />
                      <Link
                        className="flex-1 truncate font-medium hover:text-accent"
                        to={`/learn/${lessonId}${state.lastSection ? `#${state.lastSection}` : ""}`}
                      >
                        {meta.title}
                      </Link>
                      <span className="text-[12.5px] text-muted">{statusLabel(m)}</span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-4 text-[13.5px] text-muted">Lessons you open will appear here.</p>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-5">
            <SectionHeading title="Reviews" description="Spaced repetition schedule" />
            {reviews.length === 0 ? (
              <p className="text-[13.5px] text-muted">Pass a mastery check to schedule your first review.</p>
            ) : (
              <ul className="space-y-2">
                {reviews.map((m) => {
                  const d = daysUntil(m.reviewDueAt!, now);
                  return (
                    <li key={m.conceptId} className="flex items-center gap-2 text-[14px]">
                      <CalendarClock className={cn("size-4 shrink-0", m.reviewDue ? "text-accent" : "text-faint")} aria-hidden />
                      <span className="flex-1 truncate">{curriculum.concepts[m.conceptId]?.title}</span>
                      {m.reviewDue ? (
                        <Link to={`/review?concept=${m.conceptId}`} className="text-[12.5px] font-medium text-accent">
                          Due now
                        </Link>
                      ) : (
                        <span className="text-[12.5px] text-muted">
                          in {d} day{d === 1 ? "" : "s"}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <SectionHeading title="Weak spots" />
            {weak.length === 0 ? (
              <p className="text-[13.5px] text-muted">None detected. Weak spots appear when recent answers on a concept drop below 60% correct.</p>
            ) : (
              <ul className="space-y-2 text-[14px]">
                {weak.map((m) => (
                  <li key={m.conceptId} className="flex items-center gap-2">
                    <TriangleAlert className="size-4 text-warning" aria-hidden />
                    <Link className="flex-1 hover:text-accent" to={`/learn/${curriculum.concepts[m.conceptId]?.lessonId}#practice`}>
                      {curriculum.concepts[m.conceptId]?.title}
                    </Link>
                    <span className="text-[12px] text-muted">{Math.round((m.recentAccuracy ?? 0) * 100)}%</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="p-5">
            <SectionHeading title="Mastered" description={`${mastered.length} concept${mastered.length === 1 ? "" : "s"}`} />
            {mastered.length === 0 ? (
              <p className="text-[13.5px] text-muted">Your mastered concepts will collect here.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {mastered.map((m) => (
                  <Badge key={m.conceptId} tone={m.source === "self-reported" ? "neutral" : "success"} title={statusLabel(m)}>
                    {curriculum.concepts[m.conceptId]?.title}
                  </Badge>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-5">
            <SectionHeading title="Projects" />
            {activeProjects.length === 0 ? (
              <EmptyState icon={<Hammer className="size-6" />} title="No active projects">
                <Link to="/projects" className="text-accent underline underline-offset-2">
                  Browse projects
                </Link>{" "}
                — they start at beginner level.
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {activeProjects.map(([id, state]) => {
                  const p = curriculum.projects.find((x) => x.id === id)!;
                  const done = Object.keys(state.milestones).length;
                  return (
                    <li key={id}>
                      <Link to={`/projects/${id}`} className="text-[14px] font-medium hover:text-accent">
                        {p.title}
                      </Link>
                      <ProgressBar className="mt-1.5" value={done / p.milestoneIds.length} label={`${p.title} milestones`} />
                      <p className="mt-1 text-[12px] text-muted">
                        {done} / {p.milestoneIds.length} milestones
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({ icon, value, label }: { icon: ReactNode; value: number | string; label: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2/50 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-muted">{icon}</div>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="text-[12px] text-muted">{label}</p>
    </div>
  );
}
