import { lazy, Suspense, useState } from "react";
import { Link, useParams } from "react-router";
import { CheckCircle2, CircleDashed, Eye, FlaskConical, Lightbulb, Play, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import { curriculum, loadProjects } from "../../content/runtime";
import type { Milestone, Project } from "../../content/schema";
import { CodeView } from "../../components/CodeView";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, ButtonLink, Card, EmptyState, PageHeader, ProgressBar, Spinner, cn, levelTone } from "../../components/ui";
import { useAsync, useDocumentTitle, useMastery } from "../../lib/hooks";
import { python } from "../../python/client";
import type { GradeResult } from "../../python/types";
import { saveCode, setMilestone, setRubric } from "../../storage/actions";
import { progressStore, useProgress } from "../../storage/store";
import { RunOutput } from "../code/RunOutput";
import { StatusIcon } from "../curriculum/status";
import { trackLabel } from "./ProjectsPage";

const CodeEditor = lazy(() => import("../../components/CodeEditor").then((m) => ({ default: m.CodeEditor })));

function BrowserMilestone({ project, milestone, done }: { project: Project; milestone: Milestone; done: boolean }) {
  const progress = useProgress();
  const key = `project:${project.id}`;
  const code = progress.code[key]?.code ?? project.milestones.find((m) => m.starterCode)?.starterCode ?? "";
  const [grade, setGrade] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [hints, setHints] = useState(0);
  const [showSolution, setShowSolution] = useState(false);

  const check = async () => {
    setBusy(true);
    const r = await python.grade(code, milestone.tests);
    setGrade(r);
    setBusy(false);
    if (r.run.status === "completed" && r.tests.every((t) => t.passed) && r.tests.length) {
      progressStore.update((p, now) => setMilestone(p, project.id, milestone.id, true, "tests", now));
    }
  };

  return (
    <div className="mt-3 space-y-3">
      <div className="overflow-hidden rounded-lg border border-border">
        <Suspense fallback={<CodeView code={code} />}>
          <CodeEditor
            value={code}
            onChange={(v) => progressStore.update((p, now) => saveCode(p, key, v, now))}
            onRun={check}
            errorLine={grade?.run.error?.line ?? null}
            label={`Project code for ${project.title}. One file shared by all milestones.`}
            minLines={14}
            fontSize={progress.settings.editorFontSize}
          />
        </Suspense>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={check} loading={busy} icon={<FlaskConical className="size-4" aria-hidden />}>
          Run milestone tests
        </Button>
        {hints < milestone.hints.length && (
          <Button variant="ghost" onClick={() => setHints((h) => h + 1)} icon={<Lightbulb className="size-4" aria-hidden />}>
            Hint {hints + 1}/{milestone.hints.length}
          </Button>
        )}
        {milestone.solution && !showSolution && (grade || done) && (
          <Button variant="ghost" onClick={() => setShowSolution(true)} icon={<Eye className="size-4" aria-hidden />}>
            Reference solution
          </Button>
        )}
      </div>
      {milestone.hints.slice(0, hints).map((h) => (
        <p key={h} className="rounded-lg border border-info/25 bg-info-soft/60 px-3 py-2 text-[14px]">
          {h}
        </p>
      ))}
      {grade && (
        <div className="overflow-hidden rounded-lg border border-border">
          <ul className="divide-y divide-border">
            {grade.tests.map((t) => (
              <li key={t.name} className="flex items-start gap-2 px-3 py-2 text-[14px]">
                {t.passed ? (
                  <CheckCircle2 className="mt-0.5 size-4 text-success" aria-label="passed" />
                ) : (
                  <XCircle className="mt-0.5 size-4 text-danger" aria-label="failed" />
                )}
                <span>
                  <span className="font-medium">{t.name}</span>
                  {!t.passed && <span className="block text-muted">{t.message}</span>}
                </span>
              </li>
            ))}
          </ul>
          {(grade.run.error || grade.run.status !== "completed" || grade.run.stdout) && <RunOutput result={grade.run} />}
        </div>
      )}
      {showSolution && milestone.solution && (
        <div className="overflow-hidden rounded-lg border border-violet/30">
          <p className="bg-violet-soft px-3 py-1.5 text-[13px] font-semibold text-violet">Reference solution for this milestone</p>
          <CodeView code={milestone.solution} />
        </div>
      )}
    </div>
  );
}

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const state = useAsync(() => loadProjects(), []);
  const progress = useProgress();
  const mastery = useMastery();
  const project = state.status === "ready" ? state.value[projectId] : undefined;
  useDocumentTitle(project?.title ?? "Project");

  if (state.status === "loading") return <Spinner label="Loading project" />;
  if (!project) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <EmptyState title="Project not found" action={<ButtonLink to="/projects">All projects</ButtonLink>} />
      </div>
    );
  }
  const ps = progress.projects[project.id];
  const done = ps ? Object.keys(ps.milestones).length : 0;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        eyebrow={
          <>
            <Link to="/projects" className="hover:text-text">
              Projects
            </Link>{" "}
            / {trackLabel[project.track]}
          </>
        }
        title={project.title}
        description={project.summary}
      />
      <div className="mb-6 flex flex-wrap gap-2">
        <Badge tone={levelTone(project.level)}>{project.level}</Badge>
        <Badge tone="neutral">~{project.estimatedHours} hours</Badge>
        <Badge tone="neutral">{project.environment === "browser" ? "Runs in the browser" : "Runs on your machine"}</Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-6">
          <Card className="p-5">
            <h2 className="mb-2 text-lg font-semibold">The problem</h2>
            <Markdown>{project.problem}</Markdown>
          </Card>
          <Card className="p-5">
            <h2 className="mb-2 text-lg font-semibold">Acceptance criteria</h2>
            <ul className="space-y-1.5 text-[14.5px]">
              {project.acceptanceCriteria.map((a) => (
                <li key={a} className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                  <Markdown inline className="text-[14.5px]">
                    {a}
                  </Markdown>
                </li>
              ))}
            </ul>
          </Card>
          {project.architecture && (
            <Card className="p-5">
              <h2 className="mb-2 text-lg font-semibold">Architecture</h2>
              <Markdown>{project.architecture}</Markdown>
            </Card>
          )}
          <Card className="p-5">
            <h2 className="mb-2 text-lg font-semibold">Setup</h2>
            <Markdown>{project.setup}</Markdown>
          </Card>

          <section aria-labelledby="milestones">
            <h2 id="milestones" className="mb-3 text-lg font-semibold">
              Milestones
            </h2>
            <ProgressBar value={done / project.milestones.length} label="Milestones complete" className="mb-4" />
            <ol className="space-y-4">
              {project.milestones.map((m, i) => {
                const isDone = Boolean(ps?.milestones[m.id]);
                return (
                  <li key={m.id}>
                    <Card className={cn("p-5", isDone && "border-success/40")}>
                      <div className="flex items-start gap-3">
                        <span
                          className={cn(
                            "flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold",
                            isDone ? "bg-success text-white" : "bg-surface-3 text-muted",
                          )}
                        >
                          {isDone ? "✓" : i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <h3 className="font-semibold">{m.title}</h3>
                          <Markdown className="mt-1 text-[14.5px]">{m.description}</Markdown>
                          {project.environment === "browser" && m.tests.length > 0 ? (
                            <BrowserMilestone project={project} milestone={m} done={isDone} />
                          ) : (
                            <label className="mt-3 flex cursor-pointer items-center gap-2 text-[14px]">
                              <input
                                type="checkbox"
                                checked={isDone}
                                onChange={(e) => progressStore.update((p, now) => setMilestone(p, project.id, m.id, e.target.checked, "self", now))}
                                className="accent-[var(--gw-accent)]"
                              />
                              I've completed this milestone and its tests pass locally
                            </label>
                          )}
                          {isDone && ps?.milestones[m.id]?.method === "self" && <p className="mt-1 text-[12px] text-faint">Self-reported</p>}
                        </div>
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ol>
          </section>

          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold">
              <FlaskConical className="size-5 text-muted" aria-hidden /> Testing
            </h2>
            <Markdown>{project.testing}</Markdown>
          </Card>

          <Card className="p-5">
            <h2 className="mb-3 text-lg font-semibold">Self-assessment rubric</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-[13.5px]">
                <thead>
                  <tr className="text-left text-muted">
                    <th className="pb-2 pr-3 font-medium">Criterion</th>
                    <th className="pb-2 pr-3 font-medium">Needs work</th>
                    <th className="pb-2 pr-3 font-medium">Meets</th>
                    <th className="pb-2 font-medium">Exceeds</th>
                  </tr>
                </thead>
                <tbody>
                  {project.rubric.map((r) => (
                    <tr key={r.criterion} className="border-t border-border align-top">
                      <th scope="row" className="py-2 pr-3 text-left font-medium">
                        {r.criterion}
                      </th>
                      {(["needsWork", "meets", "exceeds"] as const).map((level) => {
                        const selected = ps?.rubric[r.criterion] === level;
                        return (
                          <td key={level} className="py-2 pr-3">
                            <button
                              onClick={() => progressStore.update((p, now) => setRubric(p, project.id, r.criterion, level, now))}
                              aria-pressed={selected}
                              className={cn(
                                "w-full rounded-md border px-2 py-1.5 text-left",
                                selected ? "border-accent bg-accent-soft" : "border-border hover:border-border-strong",
                              )}
                            >
                              {r[level]}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <aside className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Prerequisites</h2>
            <ul className="space-y-1.5 text-[14px]">
              {project.concepts.map((id) => {
                const c = curriculum.concepts[id]!;
                return (
                  <li key={id} className="flex items-center gap-2">
                    {mastery[id] ? <StatusIcon status={mastery[id]!.status} className="size-4" /> : <CircleDashed className="size-4" aria-hidden />}
                    <Link className="hover:text-accent" to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`}>
                      {c.title}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>
          <Card className="p-4">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <ShieldAlert className="size-4" aria-hidden /> Security
            </h2>
            <ul className="list-disc space-y-1 pl-4 text-[13.5px]">
              {project.security.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </Card>
          <Card className="p-4">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Sparkles className="size-4" aria-hidden /> Extensions
            </h2>
            <ul className="list-disc space-y-1 pl-4 text-[13.5px]">
              {project.extensions.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </Card>
          {project.starterKit && (
            <Card className="p-4 text-[13.5px]">
              <h2 className="mb-1 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
                <Play className="size-4" aria-hidden /> Starter kit
              </h2>
              <p>
                In the repository at <code className="rounded bg-surface-2 px-1 font-mono text-[12.5px]">{project.starterKit}</code>
              </p>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
