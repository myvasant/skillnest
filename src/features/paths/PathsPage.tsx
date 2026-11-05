import { Link } from "react-router";
import { CheckCircle2, Route, Target } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { activePathId } from "../../engine/recommend";
import { useDocumentTitle, useMastery } from "../../lib/hooks";
import { updateSettings } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";
import { Badge, Button, ButtonLink, Card, PageHeader, ProgressBar } from "../../components/ui";

export function PathsPage() {
  useDocumentTitle("Learning paths");
  const progress = useProgress();
  const mastery = useMastery();
  const active = activePathId(curriculum, progress);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Learning paths"
        description="Pick a goal. Each path is generated from the shared prerequisite graph — the targets you need plus everything they depend on, in a valid learning order. Nothing is duplicated between paths."
      />
      <div className="grid gap-5 md:grid-cols-2">
        {curriculum.paths.map((p) => {
          const lessons = p.conceptIds.filter((id) => curriculum.concepts[id]?.lessonId);
          const done = p.conceptIds.filter((id) => mastery[id]?.status === "mastered").length;
          const isActive = p.id === active;
          return (
            <Card key={p.id} className={isActive ? "p-5 ring-2 ring-accent/50" : "p-5"}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
                    <Route className="size-4.5 text-accent" aria-hidden />
                    {p.title}
                  </h2>
                  <p className="mt-0.5 text-[13.5px] text-muted">{p.role}</p>
                </div>
                {isActive && <Badge tone="accent">Your path</Badge>}
              </div>
              <p className="mt-3 text-[14px]">{p.summary}</p>
              <ul className="mt-3 space-y-1 text-[13.5px] text-muted">
                {p.outcomes.slice(0, 4).map((o) => (
                  <li key={o} className="flex gap-2">
                    <Target className="mt-0.5 size-3.5 shrink-0 text-faint" aria-hidden />
                    {o}
                  </li>
                ))}
              </ul>
              <ProgressBar className="mt-4" value={p.conceptIds.length ? done / p.conceptIds.length : 0} label={`${p.title} progress`} tone="success" />
              <p className="mt-1.5 text-[12.5px] text-muted">
                {p.conceptIds.length} concepts · {lessons.length} with full lessons · {done} mastered
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <ButtonLink to={`/paths/${p.id}`} variant={isActive ? "primary" : "secondary"}>
                  View path
                </ButtonLink>
                {!isActive && (
                  <Button
                    onClick={() => progressStore.update((s, now) => updateSettings(s, { activePath: p.id }, now))}
                    icon={<CheckCircle2 className="size-4" aria-hidden />}
                  >
                    Make this my path
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>
      <p className="mt-6 text-[13.5px] text-muted">
        Already experienced? Open a path and use <strong>Skip what you know</strong> to take a short diagnostic instead of working through every introductory
        lesson.{" "}
        <Link to="/curriculum" className="text-accent underline">
          Browse the full curriculum
        </Link>{" "}
        to see every concept.
      </p>
    </div>
  );
}
