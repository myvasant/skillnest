import { useMemo } from "react";
import { Link, useParams } from "react-router";
import {
  AlertTriangle,
  ArrowLeftRight,
  BookOpen,
  Briefcase,
  CheckCircle2,
  CircleDashed,
  GitFork,
  Hammer,
  KeyRound,
  MessagesSquare,
  Wrench,
} from "lucide-react";
import { curriculum, stageById } from "../../content/runtime";
import { ancestors } from "../../engine/layout";
import { useDocumentTitle, useMastery } from "../../lib/hooks";
import { setDiagnostic } from "../../storage/actions";
import { progressStore } from "../../storage/store";
import { Badge, Button, ButtonLink, Card, EmptyState, levelTone } from "../../components/ui";
import { SourceList } from "../../components/SourceList";
import { ConceptGraph } from "./ConceptGraph";
import { StatusIcon, statusLabel } from "./status";

function ConceptLink({ id }: { id: string }) {
  const c = curriculum.concepts[id];
  if (!c) return <span>{id}</span>;
  return (
    <Link to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`} className="hover:text-accent">
      {c.title}
    </Link>
  );
}

export function ConceptPage() {
  const { conceptId = "" } = useParams();
  const concept = curriculum.concepts[conceptId];
  const mastery = useMastery();
  useDocumentTitle(concept?.title ?? "Concept");

  const chain = useMemo(() => {
    if (!concept) return [];
    const up = ancestors(concept.id, (id) => curriculum.concepts[id]?.requires ?? []);
    return curriculum.conceptOrder.filter((id) => up.has(id));
  }, [concept]);

  if (!concept) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <EmptyState title="Concept not found" action={<ButtonLink to="/curriculum">Browse the curriculum</ButtonLink>}>
          No concept has the id “{conceptId}”.
        </EmptyState>
      </div>
    );
  }

  const m = mastery[concept.id]!;
  const stage = stageById(concept.stage)!;
  const module = stage.modules.find((x) => x.id === concept.module);
  const neighbourhood = [...new Set([...concept.requires, concept.id, ...concept.requiredBy])];
  const glossary = curriculum.glossary.filter((g) => concept.glossaryIds.includes(g.id));
  const projects = curriculum.projects.filter((p) => concept.projectIds.includes(p.id));

  return (
    <div className="mx-auto max-w-5xl">
      <nav aria-label="Breadcrumb" className="mb-4 text-[13px] text-muted">
        <Link to="/curriculum" className="hover:text-text">
          Curriculum
        </Link>{" "}
        /{" "}
        <Link to={`/curriculum?stage=${stage.id}`} className="hover:text-text">
          {stage.shortTitle}
        </Link>{" "}
        / <span className="text-text">{module?.title}</span>
      </nav>
      <header className="mb-6">
        <div className="mb-2 flex flex-wrap gap-2">
          <Badge tone={levelTone(concept.level)}>{concept.level}</Badge>
          <Badge tone="neutral">{concept.priority}</Badge>
          <Badge tone={m.status === "mastered" ? "success" : "neutral"}>
            <StatusIcon status={m.status} className="size-3" /> {statusLabel(m)}
          </Badge>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">{concept.title}</h1>
        <p className="mt-3 max-w-3xl text-[16px] leading-relaxed">{concept.summary}</p>
        {concept.why && (
          <p className="mt-2 max-w-3xl text-[15px] text-muted">
            <span className="font-medium text-text">Why it matters: </span>
            {concept.why}
          </p>
        )}
      </header>

      <Card className="mb-6 flex flex-wrap items-center gap-4 p-5">
        <BookOpen className="size-6 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          {concept.lessonId ? (
            <>
              <p className="font-semibold">Full interactive lesson available</p>
              <p className="text-[13.5px] text-muted">{curriculum.lessons[concept.lessonId]?.summary.replace(/`/g, "")}</p>
            </>
          ) : (
            <>
              <p className="font-semibold">Outline only — the full lesson is planned</p>
              <p className="text-[13.5px] text-muted">Use the key ideas, misconceptions and official sources below. See ROADMAP.md for the content plan.</p>
            </>
          )}
        </div>
        {concept.lessonId && (
          <ButtonLink to={`/learn/${concept.lessonId}`} variant="primary">
            Open lesson
          </ButtonLink>
        )}
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        {concept.keyIdeas.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <KeyRound className="size-4" aria-hidden /> Key ideas
            </h2>
            <ul className="list-disc space-y-1.5 pl-5 text-[14.5px]">
              {concept.keyIdeas.map((k) => (
                <li key={k}>{k.replace(/`/g, "")}</li>
              ))}
            </ul>
          </Card>
        )}
        {concept.misconceptions.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <AlertTriangle className="size-4" aria-hidden /> Common misconceptions
            </h2>
            <ul className="list-disc space-y-1.5 pl-5 text-[14.5px]">
              {concept.misconceptions.map((k) => (
                <li key={k}>{k.replace(/`/g, "")}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <section className="mt-8">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <GitFork className="size-5 text-muted" aria-hidden /> Where it sits
        </h2>
        <ConceptGraph conceptIds={neighbourhood} mastery={mastery} />
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card className="p-4">
            <h3 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Full prerequisite chain ({chain.length})</h3>
            {chain.length === 0 ? (
              <p className="text-[14px] text-muted">None — this is a starting point.</p>
            ) : (
              <ol className="space-y-1 text-[14px]">
                {chain.map((id) => {
                  const ok = mastery[id]?.status === "mastered" || mastery[id]?.status === "proficient";
                  return (
                    <li key={id} className="flex items-center gap-2">
                      {ok ? (
                        <CheckCircle2 className="size-3.5 text-success" aria-label="satisfied" />
                      ) : (
                        <CircleDashed className="size-3.5 text-faint" aria-label="not yet" />
                      )}
                      <ConceptLink id={id} />
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
          <Card className="p-4">
            <h3 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Unlocks ({concept.requiredBy.length})</h3>
            {concept.requiredBy.length === 0 ? (
              <p className="text-[14px] text-muted">Nothing requires this directly yet.</p>
            ) : (
              <ul className="space-y-1 text-[14px]">
                {concept.requiredBy.map((id) => (
                  <li key={id}>
                    <ConceptLink id={id} />
                  </li>
                ))}
              </ul>
            )}
            {(concept.extends.length > 0 || concept.extendedBy.length > 0) && (
              <p className="mt-3 text-[13.5px] text-muted">
                {concept.extends.length > 0 && (
                  <>
                    Extends:{" "}
                    {concept.extends.map((id, i) => (
                      <span key={id}>
                        {i > 0 && ", "}
                        <ConceptLink id={id} />
                      </span>
                    ))}
                    .{" "}
                  </>
                )}
                {concept.extendedBy.length > 0 && (
                  <>
                    Extended by:{" "}
                    {concept.extendedBy.map((id, i) => (
                      <span key={id}>
                        {i > 0 && ", "}
                        <ConceptLink id={id} />
                      </span>
                    ))}
                    .
                  </>
                )}
              </p>
            )}
          </Card>
        </div>
      </section>

      {(concept.contrastsWith.length > 0 || concept.confusedWith.length > 0) && (
        <Card className="mt-6 p-5">
          <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
            <ArrowLeftRight className="size-4" aria-hidden /> Compare and contrast
          </h2>
          {concept.contrastsWith.length > 0 && (
            <p className="text-[14px]">
              Contrasts with:{" "}
              {concept.contrastsWith.map((id, i) => (
                <span key={id}>
                  {i > 0 && ", "}
                  <ConceptLink id={id} />
                </span>
              ))}
            </p>
          )}
          {concept.confusedWith.length > 0 && (
            <p className="mt-1 text-[14px]">
              Commonly confused with:{" "}
              {concept.confusedWith.map((id, i) => (
                <span key={id}>
                  {i > 0 && ", "}
                  <ConceptLink id={id} />
                </span>
              ))}
            </p>
          )}
        </Card>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        {(concept.interview || concept.interviewIds.length > 0) && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <MessagesSquare className="size-4" aria-hidden /> Interview angle
            </h2>
            {concept.interview && <p className="text-[14.5px]">{concept.interview.replace(/`/g, "")}</p>}
            {concept.interviewIds.length > 0 && (
              <Link to={`/interview?concept=${concept.id}`} className="mt-2 inline-block text-[13.5px] text-accent underline underline-offset-2">
                {concept.interviewIds.length} practice question{concept.interviewIds.length === 1 ? "" : "s"} →
              </Link>
            )}
          </Card>
        )}
        {concept.production && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Briefcase className="size-4" aria-hidden /> In production
            </h2>
            <p className="text-[14.5px]">{concept.production}</p>
          </Card>
        )}
        {concept.tools.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Wrench className="size-4" aria-hidden /> Tools
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {concept.tools.map((t) => (
                <Badge key={t}>{t}</Badge>
              ))}
            </div>
          </Card>
        )}
        {projects.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Hammer className="size-4" aria-hidden /> Applied in projects
            </h2>
            <ul className="space-y-1 text-[14px]">
              {projects.map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${p.id}`} className="hover:text-accent">
                    {p.title}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {glossary.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Terms</h2>
            <dl className="space-y-2 text-[14px]">
              {glossary.map((g) => (
                <div key={g.id}>
                  <dt className="font-medium">{g.term}</dt>
                  <dd className="text-muted">{g.definition.replace(/`/g, "")}</dd>
                </div>
              ))}
            </dl>
          </Card>
        )}
        {concept.sources.length > 0 && (
          <Card className="p-5">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Official sources</h2>
            <SourceList sources={concept.sources} />
          </Card>
        )}
      </div>

      <Card className="mt-6 p-5">
        <h2 className="mb-1 text-[15px] font-semibold">Already know this?</h2>
        {concept.lessonId && curriculum.lessons[concept.lessonId]?.masteryItemIds.length ? (
          <p className="text-[14px] text-muted">
            Prove it and skip ahead: take the lesson's{" "}
            <Link to={`/learn/${concept.lessonId}#mastery-check`} className="text-accent underline">
              mastery check
            </Link>{" "}
            directly. Passing it counts exactly like finishing the lesson.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-3 text-[14px] text-muted">
            <span>There is no assessment for this concept yet. You can mark it as known; it will be labelled “self-reported”.</span>
            {m.source === "self-reported" ? (
              <Button size="sm" onClick={() => progressStore.update((p, now) => setDiagnostic(p, concept.id, null, now))}>
                Undo “known”
              </Button>
            ) : (
              <Button size="sm" onClick={() => progressStore.update((p, now) => setDiagnostic(p, concept.id, "self-reported", now))}>
                Mark as known
              </Button>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
