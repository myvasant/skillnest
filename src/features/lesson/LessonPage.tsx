import { useEffect, useMemo, useRef } from "react";
import { Link, useLocation, useParams } from "react-router";
import { BookOpenCheck, CheckCircle2, ChevronLeft, ChevronRight, CircleDashed, Clock, ListChecks, Microscope, Target } from "lucide-react";
import { curriculum, loadLesson, stageById } from "../../content/runtime";
import type { Lesson } from "../../content/schema";
import { Markdown } from "../../components/Markdown";
import { SourceList } from "../../components/SourceList";
import { Badge, ButtonLink, Card, ProgressBar, Spinner, cn, levelTone } from "../../components/ui";
import { useAsync, useDocumentTitle, useMastery } from "../../lib/hooks";
import { python } from "../../python/client";
import { seeSection, updateSettings, visitLesson } from "../../storage/actions";
import { progressStore, useProgressSelector } from "../../storage/store";
import { StatusIcon, statusLabel } from "../curriculum/status";
import { DeepBadge, LessonBlock } from "./LessonBlocks";
import { MasteryCheck } from "./MasteryCheck";

/** Previous / next lesson along the active learning path (falls back to the global curriculum order). */
function LessonNeighbours({ conceptId }: { conceptId: string }) {
  const progress = useProgressSelector((p) => p.settings.activePath);
  const path = curriculum.paths.find((p) => p.id === (progress ?? curriculum.defaultPath));
  const order = (path && path.conceptIds.includes(conceptId) ? path.conceptIds : curriculum.conceptOrder).filter((id) => curriculum.concepts[id]?.lessonId);
  const i = order.indexOf(conceptId);
  const prev = i > 0 ? curriculum.concepts[order[i - 1]!] : undefined;
  const next = i >= 0 && i < order.length - 1 ? curriculum.concepts[order[i + 1]!] : undefined;
  if (!prev && !next) return null;
  return (
    <nav aria-label="Lesson navigation" className="mt-12 grid gap-3 sm:grid-cols-2">
      {prev ? (
        <Link to={`/learn/${prev.lessonId}`} className="rounded-xl border border-border bg-surface p-4 shadow-card hover:border-accent">
          <span className="flex items-center gap-1 text-[12px] text-muted">
            <ChevronLeft className="size-3.5" aria-hidden /> Previous lesson
          </span>
          <span className="mt-0.5 block font-medium">{prev.title}</span>
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link to={`/learn/${next.lessonId}`} className="rounded-xl border border-border bg-surface p-4 text-right shadow-card hover:border-accent">
          <span className="flex items-center justify-end gap-1 text-[12px] text-muted">
            Next lesson <ChevronRight className="size-3.5" aria-hidden />
          </span>
          <span className="mt-0.5 block font-medium">{next.title}</span>
        </Link>
      )}
    </nav>
  );
}

export function LessonPage() {
  const { lessonId = "" } = useParams();
  const state = useAsync(() => loadLesson(lessonId), [lessonId]);
  if (state.status === "loading")
    return (
      <div className="py-20 text-center">
        <Spinner label="Loading lesson" />
      </div>
    );
  if (state.status === "error" || !state.value) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <h1 className="text-xl font-semibold">Lesson not found</h1>
        <p className="mt-2 text-muted">There is no lesson called “{lessonId}”. It may not be written yet.</p>
        <ButtonLink className="mt-4" to="/curriculum" variant="primary">
          Browse the curriculum
        </ButtonLink>
      </div>
    );
  }
  return <LessonView lesson={state.value} />;
}

function LessonView({ lesson }: { lesson: Lesson }) {
  const location = useLocation();
  const meta = curriculum.lessons[lesson.id]!;
  const concept = curriculum.concepts[lesson.concept]!;
  const stage = stageById(concept.stage);
  const mastery = useMastery();
  const showDeep = useProgressSelector((p) => p.settings.showDeepDives);
  const lessonState = useProgressSelector((p) => p.lessons[lesson.id]);
  const seen = useMemo(() => new Set(lessonState?.sectionsSeen ?? []), [lessonState]);
  const sectionRefs = useRef(new Map<string, HTMLElement>());
  useDocumentTitle(lesson.title);

  // Record the visit and warm up the Python runtime in the background.
  useEffect(() => {
    progressStore.update((p, now) => visitLesson(p, lesson.id, lesson.title, `/learn/${lesson.id}`, now));
    const hasPython = lesson.sections.some((s) => s.blocks.some((b) => (b.type === "code" && b.runnable) || b.type === "item" || b.type === "visualization"));
    if (hasPython) {
      const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback;
      if (idle) idle(() => void python.preload().catch(() => undefined));
      else setTimeout(() => void python.preload().catch(() => undefined), 800);
    }
  }, [lesson]);

  // Scroll to the section named in the URL hash (resume support).
  useEffect(() => {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) {
      window.scrollTo({ top: 0 });
      return;
    }
    const t = setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 60);
    return () => clearTimeout(t);
  }, [location.hash, lesson.id]);

  // Mark sections as seen when they are substantially on screen.
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const id = entry.target.id;
          const section = lesson.sections.find((s) => s.id === id);
          if (section) progressStore.update((p, now) => seeSection(p, lesson.id, id, `${lesson.title} — ${section.title}`, now));
        }
      },
      { rootMargin: "0px 0px -55% 0px", threshold: 0 },
    );
    sectionRefs.current.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [lesson, showDeep]);

  const coreSections = lesson.sections.filter((s) => s.depth === "core");
  const coreSeen = coreSections.filter((s) => seen.has(s.id)).length;
  const conceptMastery = mastery[lesson.concept];

  return (
    <div className="mx-auto flex max-w-[1180px] gap-10">
      <article className="min-w-0 flex-1 pb-24">
        <nav aria-label="Breadcrumb" className="mb-4 text-[13px] text-muted">
          <ol className="flex flex-wrap items-center gap-1.5">
            <li>
              <Link className="hover:text-text" to="/curriculum">
                Curriculum
              </Link>
            </li>
            <li aria-hidden>/</li>
            <li>
              <Link className="hover:text-text" to={`/curriculum?stage=${stage?.id}`}>
                {stage?.shortTitle}
              </Link>
            </li>
            <li aria-hidden>/</li>
            <li aria-current="page" className="text-text">
              {lesson.title}
            </li>
          </ol>
        </nav>

        <header className="mb-8">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone={levelTone(concept.level)}>{concept.level}</Badge>
            <Badge tone="neutral">
              <Clock className="size-3" aria-hidden /> {lesson.estimatedMinutes} min
            </Badge>
            {conceptMastery && (
              <Badge tone={conceptMastery.status === "mastered" ? "success" : conceptMastery.status === "not-started" ? "neutral" : "info"}>
                <StatusIcon status={conceptMastery.status} className="size-3" /> {statusLabel(conceptMastery)}
              </Badge>
            )}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-[34px]">{lesson.title}</h1>
          {lesson.subtitle && <p className="mt-1 text-lg text-muted">{lesson.subtitle}</p>}
          <p className="mt-4 max-w-3xl text-[16px] leading-relaxed text-text">{lesson.summary.replace(/`/g, "")}</p>
        </header>

        <div className="mb-10 grid gap-4 md:grid-cols-2">
          <Card className="p-4">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <Target className="size-4" aria-hidden /> You will be able to
            </h2>
            <ul className="space-y-1.5 text-[14px]">
              {lesson.objectives.map((o) => (
                <li key={o} className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-4">
            <h2 className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <ListChecks className="size-4" aria-hidden /> Before you start
            </h2>
            {concept.requires.length === 0 ? (
              <p className="text-[14px] text-muted">No prerequisites — this is a starting point.</p>
            ) : (
              <ul className="space-y-1.5 text-[14px]">
                {concept.requires.map((id) => {
                  const pre = curriculum.concepts[id]!;
                  const m = mastery[id]!;
                  const ok = m.status === "mastered" || m.status === "proficient";
                  return (
                    <li key={id} className="flex items-start gap-2">
                      {ok ? (
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="satisfied" />
                      ) : (
                        <CircleDashed className="mt-0.5 size-4 shrink-0 text-warning" aria-label="not yet mastered" />
                      )}
                      <span>
                        <Link className="font-medium hover:text-accent" to={pre.lessonId ? `/learn/${pre.lessonId}` : `/concept/${id}`}>
                          {pre.title}
                        </Link>
                        <span className="block text-[12.5px] text-muted">
                          {ok ? statusLabel(m) : pre.lessonId ? "Not mastered yet — worth a quick check." : "Outline only (no lesson yet): skim the summary."}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <div className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-2/60 px-4 py-2.5">
          <span className="text-[13.5px] text-muted">Plain explanations first. Deep dives add internals and edge cases.</span>
          <label className="flex cursor-pointer items-center gap-2 text-[13.5px] font-medium">
            <input
              type="checkbox"
              role="switch"
              checked={showDeep}
              onChange={(e) => progressStore.update((p, now) => updateSettings(p, { showDeepDives: e.target.checked }, now))}
              className="accent-[var(--gw-accent)]"
            />
            <Microscope className="size-4 text-muted" aria-hidden /> Show deep dives
          </label>
        </div>

        {lesson.sections.map((section) => {
          if (section.depth === "deep" && !showDeep) {
            return (
              <div
                key={section.id}
                id={section.id}
                className="mb-10 flex items-center justify-between rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted"
              >
                <span className="flex items-center gap-2">
                  <DeepBadge /> {section.title}
                </span>
                <button
                  className="text-accent underline underline-offset-2"
                  onClick={() => progressStore.update((p, now) => updateSettings(p, { showDeepDives: true }, now))}
                >
                  Show
                </button>
              </div>
            );
          }
          return (
            <section
              key={section.id}
              id={section.id}
              ref={(el) => {
                if (el) sectionRefs.current.set(section.id, el);
                else sectionRefs.current.delete(section.id);
              }}
              className="mb-12 scroll-mt-24"
              aria-labelledby={`${section.id}-title`}
            >
              <h2 id={`${section.id}-title`} className="mb-4 flex items-center gap-2 text-[22px] font-semibold tracking-tight">
                {section.title}
                {section.depth === "deep" && <DeepBadge />}
              </h2>
              {section.blocks.map((block, i) => {
                if (block.depth === "deep" && !showDeep) return null;
                return <LessonBlock key={i} block={block} lesson={lesson} index={i} sectionId={section.id} />;
              })}
            </section>
          );
        })}

        <MasteryCheck lesson={lesson} />

        {lesson.cheatsheet && (
          <section className="mt-12" aria-labelledby="cheatsheet-title">
            <h2 id="cheatsheet-title" className="mb-3 flex items-center gap-2 text-[22px] font-semibold tracking-tight">
              <BookOpenCheck className="size-5 text-accent" aria-hidden /> Cheat sheet
            </h2>
            <Card className="p-5">
              <Markdown>{lesson.cheatsheet}</Markdown>
            </Card>
          </section>
        )}

        <LessonNeighbours conceptId={lesson.concept} />

        <section className="mt-12 grid gap-4 md:grid-cols-2">
          <Card className="p-4">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Where this leads</h2>
            {concept.requiredBy.length === 0 ? (
              <p className="text-[14px] text-muted">Nothing depends on this yet.</p>
            ) : (
              <ul className="space-y-1 text-[14px]">
                {concept.requiredBy.slice(0, 8).map((id) => {
                  const c = curriculum.concepts[id]!;
                  return (
                    <li key={id}>
                      <Link className="hover:text-accent" to={c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`}>
                        {c.title}
                      </Link>
                      {!c.lessonId && <span className="text-[12px] text-faint"> · outline</span>}
                    </li>
                  );
                })}
              </ul>
            )}
            <Link to={`/concept/${concept.id}`} className="mt-3 inline-block text-[13px] text-accent underline underline-offset-2">
              Concept map, interview questions and projects →
            </Link>
          </Card>
          <Card className="p-4">
            <h2 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">Sources</h2>
            <SourceList sources={lesson.sources} />
            <p className="mt-3 text-[12px] text-faint">Content reviewed {meta.reviewedOn}. Code verified by automated tests against Python 3.14 (Pyodide).</p>
          </Card>
        </section>
      </article>

      <aside className="sticky top-20 hidden h-[calc(100vh-6rem)] w-60 shrink-0 overflow-y-auto pb-8 xl:block" aria-label="Lesson contents">
        <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">On this page</p>
        <ProgressBar value={coreSections.length ? coreSeen / coreSections.length : 0} label="Sections read" className="mb-3" />
        <ol className="space-y-0.5 text-[13.5px]">
          {lesson.sections.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className={cn("flex items-center gap-2 rounded-md px-2 py-1 hover:bg-surface-2", seen.has(s.id) ? "text-text" : "text-muted")}
              >
                {seen.has(s.id) ? (
                  <CheckCircle2 className="size-3.5 shrink-0 text-success" aria-label="read" />
                ) : (
                  <span className="size-3.5 shrink-0 rounded-full border border-border-strong" aria-hidden />
                )}
                <span className="truncate">{s.title}</span>
              </a>
            </li>
          ))}
          {lesson.masteryCheck && (
            <li>
              <a href="#mastery-check" className="flex items-center gap-2 rounded-md px-2 py-1 font-medium text-accent hover:bg-surface-2">
                <BookOpenCheck className="size-3.5 shrink-0" aria-hidden /> Mastery check
              </a>
            </li>
          )}
        </ol>
      </aside>
    </div>
  );
}
