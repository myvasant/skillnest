import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { BookOpen, Filter, LayoutGrid, List, Network } from "lucide-react";
import { curriculum } from "../../content/runtime";
import type { Level, Priority } from "../../content/schema";
import type { MasteryStatus } from "../../engine/mastery";
import { useDocumentTitle, useMastery } from "../../lib/hooks";
import { Badge, Card, PageHeader, ProgressBar, cn, levelTone } from "../../components/ui";
import { ConceptGraph } from "./ConceptGraph";
import { StatusIcon, statusLabel } from "./status";

const priorityLabel: Record<Priority, string> = {
  essential: "Essential foundation",
  supporting: "Supporting knowledge",
  advanced: "Advanced specialization",
  optional: "Optional enrichment",
  "technology-specific": "Technology-specific",
};

function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | "";
  options: { value: T; label: string }[];
  onChange: (v: T | "") => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[13px] text-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T | "")}
        className="h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CurriculumPage() {
  useDocumentTitle("Curriculum");
  const [params, setParams] = useSearchParams();
  const mastery = useMastery();
  const stageId = params.get("stage") ?? "";
  const view = params.get("view") ?? "graph";
  const level = (params.get("level") ?? "") as Level | "";
  const priority = (params.get("priority") ?? "") as Priority | "";
  const status = (params.get("status") ?? "") as MasteryStatus | "";
  const pathId = params.get("path") ?? "";
  const lessonsOnly = params.get("lessons") === "1";

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const pathSet = useMemo(() => (pathId ? new Set(curriculum.paths.find((p) => p.id === pathId)?.conceptIds ?? []) : null), [pathId]);
  const matches = useMemo(() => {
    const out = new Set<string>();
    for (const id of curriculum.conceptOrder) {
      const c = curriculum.concepts[id]!;
      if (level && c.level !== level) continue;
      if (priority && c.priority !== priority) continue;
      if (status && mastery[id]?.status !== status) continue;
      if (lessonsOnly && !c.lessonId) continue;
      if (pathSet && !pathSet.has(id)) continue;
      out.add(id);
    }
    return out;
  }, [level, priority, status, lessonsOnly, pathSet, mastery]);
  const filtering = Boolean(level || priority || status || lessonsOnly || pathSet);
  const stage = curriculum.stages.find((s) => s.id === stageId);

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Curriculum"
        description={`${curriculum.stats.stages} stages · ${curriculum.stats.concepts} concepts connected by prerequisites · ${curriculum.stats.lessons} full lessons so far. Concepts without a lesson show an outline: summary, key ideas, misconceptions, prerequisites and official sources.`}
      />

      <Card className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3">
        <Filter className="size-4 text-muted" aria-hidden />
        <Select
          label="Level"
          value={level}
          onChange={(v) => update("level", v)}
          options={[
            { value: "beginner", label: "Beginner" },
            { value: "intermediate", label: "Intermediate" },
            { value: "advanced", label: "Advanced" },
          ]}
        />
        <Select
          label="Priority"
          value={priority}
          onChange={(v) => update("priority", v)}
          options={(Object.keys(priorityLabel) as Priority[]).map((p) => ({ value: p, label: priorityLabel[p] }))}
        />
        <Select
          label="Progress"
          value={status}
          onChange={(v) => update("status", v)}
          options={[
            { value: "not-started", label: "Not started" },
            { value: "learning", label: "Learning" },
            { value: "proficient", label: "Proficient" },
            { value: "mastered", label: "Mastered" },
          ]}
        />
        <Select label="Goal" value={pathId} onChange={(v) => update("path", v)} options={curriculum.paths.map((p) => ({ value: p.id, label: p.title }))} />
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <input type="checkbox" checked={lessonsOnly} onChange={(e) => update("lessons", e.target.checked ? "1" : "")} className="accent-[var(--gw-accent)]" />
          Has a lesson
        </label>
        {filtering && <span className="ml-auto text-[13px] text-muted">{matches.size} matching concepts</span>}
      </Card>

      <nav aria-label="Stages" className="mb-6 flex flex-wrap gap-1.5">
        <button
          onClick={() => update("stage", "")}
          className={cn(
            "rounded-full border px-3 py-1 text-[13px]",
            !stageId ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text",
          )}
        >
          <LayoutGrid className="mr-1 inline size-3.5" aria-hidden />
          All stages
        </button>
        {curriculum.stages.map((s) => (
          <button
            key={s.id}
            onClick={() => update("stage", s.id)}
            aria-current={stageId === s.id ? "true" : undefined}
            className={cn(
              "rounded-full border px-3 py-1 text-[13px]",
              stageId === s.id ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text",
            )}
          >
            {s.order}. {s.shortTitle}
          </button>
        ))}
      </nav>

      {!stage && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {curriculum.stages.map((s) => {
            const ids = s.conceptIds.filter((id) => !filtering || matches.has(id));
            const lessons = s.conceptIds.filter((id) => curriculum.concepts[id]!.lessonId).length;
            const done = s.conceptIds.filter((id) => mastery[id]?.status === "mastered").length;
            return (
              <Card key={s.id} className={cn("flex flex-col p-5", filtering && ids.length === 0 && "opacity-50")}>
                <p className="text-[12px] font-semibold uppercase tracking-wide text-faint">Stage {s.order}</p>
                <button onClick={() => update("stage", s.id)} className="mt-1 text-left text-[17px] font-semibold tracking-tight hover:text-accent">
                  {s.title}
                </button>
                <p className="mt-1.5 flex-1 text-[13.5px] leading-relaxed text-muted">{s.summary}</p>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  <Badge tone="neutral">{s.conceptIds.length} concepts</Badge>
                  <Badge tone={lessons ? "accent" : "neutral"}>
                    <BookOpen className="size-3" aria-hidden /> {lessons} lessons
                  </Badge>
                  {filtering && <Badge tone="info">{ids.length} match</Badge>}
                </div>
                <ProgressBar className="mt-3" value={s.conceptIds.length ? done / s.conceptIds.length : 0} label={`${s.title} mastery`} tone="success" />
              </Card>
            );
          })}
        </div>
      )}

      {stage && (
        <>
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div className="max-w-3xl">
              <h2 className="text-xl font-semibold tracking-tight">
                Stage {stage.order}: {stage.title}
              </h2>
              <p className="mt-1 text-[14px] text-muted">{stage.summary}</p>
              <p className="mt-1 text-[14px] text-text">
                <span className="font-medium">Why it matters: </span>
                {stage.why}
              </p>
            </div>
            <div role="tablist" aria-label="View" className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
              {[
                { id: "graph", label: "Graph", icon: Network },
                { id: "list", label: "List", icon: List },
              ].map((v) => (
                <button
                  key={v.id}
                  role="tab"
                  aria-selected={view === v.id}
                  onClick={() => update("view", v.id === "graph" ? "" : v.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium",
                    view === v.id ? "bg-surface text-text shadow-card" : "text-muted",
                  )}
                >
                  <v.icon className="size-4" aria-hidden /> {v.label}
                </button>
              ))}
            </div>
          </div>

          {view === "graph" ? (
            <>
              <ConceptGraph conceptIds={stage.conceptIds} mastery={mastery} filtered={filtering ? matches : undefined} />
              <p className="mt-2 text-[12.5px] text-muted">
                Arrows point from a prerequisite to the concept that needs it. Hover or Tab to a node to highlight its prerequisite chain. The coloured bar
                shows your status. Prefer text?{" "}
                <button className="text-accent underline" onClick={() => update("view", "list")}>
                  Switch to the list view
                </button>
                .
              </p>
            </>
          ) : (
            <div className="space-y-6">
              {stage.modules.map((m) => {
                const ids = m.conceptIds.filter((id) => !filtering || matches.has(id));
                if (!ids.length) return null;
                return (
                  <section key={m.id} aria-labelledby={`mod-${m.id}`}>
                    <h3 id={`mod-${m.id}`} className="text-[15px] font-semibold">
                      {m.title}
                    </h3>
                    <p className="mb-2 text-[13px] text-muted">{m.summary}</p>
                    <Card>
                      <ul className="divide-y divide-border">
                        {ids.map((id) => {
                          const c = curriculum.concepts[id]!;
                          const ms = mastery[id]!;
                          return (
                            <li key={id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                              <StatusIcon status={ms.status} className="size-4" />
                              <div className="min-w-0 flex-1">
                                <Link to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`} className="font-medium hover:text-accent">
                                  {c.title}
                                </Link>
                                <p className="truncate text-[12.5px] text-muted">{c.summary}</p>
                              </div>
                              <Badge tone={levelTone(c.level)}>{c.level}</Badge>
                              {c.priority !== "essential" && <Badge tone="neutral">{priorityLabel[c.priority]}</Badge>}
                              {c.lessonId ? <Badge tone="accent">Lesson</Badge> : <Badge tone="neutral">Outline</Badge>}
                              <span className="w-32 text-right text-[12px] text-muted">{statusLabel(ms)}</span>
                            </li>
                          );
                        })}
                      </ul>
                    </Card>
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
