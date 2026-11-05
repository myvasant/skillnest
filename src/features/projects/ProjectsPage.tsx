import { Link } from "react-router";
import { Globe2, Hammer, Laptop } from "lucide-react";
import { curriculum } from "../../content/runtime";
import type { Project } from "../../content/schema";
import { useDocumentTitle } from "../../lib/hooks";
import { useProgress } from "../../storage/store";
import { Badge, Card, EmptyState, PageHeader, ProgressBar, levelTone } from "../../components/ui";

export const trackLabel: Record<Project["track"], string> = {
  "python-beginner": "Beginner Python",
  "python-intermediate": "Intermediate Python",
  backend: "Backend & databases",
  "data-ml": "Data & machine learning",
  "genai-rag": "Generative AI & RAG",
  agentic: "Agentic AI",
  production: "Production engineering",
};

export function ProjectsPage() {
  useDocumentTitle("Projects");
  const progress = useProgress();
  const tracks = Object.keys(trackLabel) as Project["track"][];
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Projects"
        description="Build real things from the start. Each project has a problem statement, acceptance criteria, milestones, automated tests, security notes and a rubric. Beginner projects run in the browser; later ones run on your machine with pytest."
      />
      {curriculum.projects.length === 0 && <EmptyState icon={<Hammer className="size-8" />} title="No projects yet" />}
      <div className="space-y-10">
        {tracks.map((track) => {
          const projects = curriculum.projects.filter((p) => p.track === track);
          if (!projects.length) return null;
          return (
            <section key={track} aria-labelledby={`track-${track}`}>
              <h2 id={`track-${track}`} className="mb-3 text-[15px] font-semibold">
                {trackLabel[track]}
              </h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {projects.map((p) => {
                  const state = progress.projects[p.id];
                  const done = state ? Object.keys(state.milestones).length : 0;
                  return (
                    <Card key={p.id} className="flex flex-col p-5">
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <Badge tone={levelTone(p.level)}>{p.level}</Badge>
                        <Badge tone="neutral">
                          {p.environment === "browser" ? <Globe2 className="size-3" aria-hidden /> : <Laptop className="size-3" aria-hidden />}
                          {p.environment === "browser" ? "In browser" : "On your machine"}
                        </Badge>
                        <Badge tone="neutral">~{p.estimatedHours} h</Badge>
                      </div>
                      <Link to={`/projects/${p.id}`} className="text-[16px] font-semibold tracking-tight hover:text-accent">
                        {p.title}
                      </Link>
                      <p className="mt-1 flex-1 text-[13.5px] text-muted">{p.summary}</p>
                      <ProgressBar className="mt-4" value={done / p.milestoneIds.length} label={`${p.title} milestones`} />
                      <p className="mt-1 text-[12px] text-muted">
                        {done} / {p.milestoneIds.length} milestones
                      </p>
                    </Card>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
