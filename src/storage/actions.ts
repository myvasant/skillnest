// Pure progress transitions. Each returns a new Progress object; the store
// persists it. Kept free of React and storage APIs so they are easy to test.
import { addDays, initialReview, interviewInterval, nextReview } from "../engine/review";
import { HISTORY_LIMIT, emptyConceptProgress, type AttemptContext, type ConceptProgress, type Progress, type Settings } from "./progress";

const stamp = (p: Progress, now: Date): Progress => ({ ...p, updatedAt: now.toISOString() });

function withConcept(p: Progress, conceptId: string, update: (c: ConceptProgress) => ConceptProgress): Progress {
  const current = p.concepts[conceptId] ?? emptyConceptProgress();
  return { ...p, concepts: { ...p.concepts, [conceptId]: update(current) } };
}

export function visitLesson(p: Progress, lessonId: string, title: string, path: string, now: Date): Progress {
  const iso = now.toISOString();
  const existing = p.lessons[lessonId];
  return stamp(
    {
      ...p,
      lessons: {
        ...p.lessons,
        [lessonId]: existing
          ? { ...existing, lastVisitedAt: iso }
          : { startedAt: iso, lastVisitedAt: iso, lastSection: null, sectionsSeen: [], completedAt: null },
      },
      lastLocation: { path, title, at: iso },
    },
    now,
  );
}

export function seeSection(p: Progress, lessonId: string, sectionId: string, title: string, now: Date): Progress {
  const lesson = p.lessons[lessonId];
  if (!lesson) return p;
  const iso = now.toISOString();
  const seen = lesson.sectionsSeen.includes(sectionId) ? lesson.sectionsSeen : [...lesson.sectionsSeen, sectionId];
  if (seen === lesson.sectionsSeen && lesson.lastSection === sectionId) return p;
  return stamp(
    {
      ...p,
      lessons: { ...p.lessons, [lessonId]: { ...lesson, sectionsSeen: seen, lastSection: sectionId, lastVisitedAt: iso } },
      lastLocation: { path: `/learn/${lessonId}#${sectionId}`, title, at: iso },
    },
    now,
  );
}

export interface AttemptInput {
  gid: string;
  correct: boolean;
  context: AttemptContext;
}

export function recordAttempt(p: Progress, attempt: AttemptInput, now: Date): Progress {
  const iso = now.toISOString();
  const prev = p.items[attempt.gid];
  const attempts = (prev?.attempts ?? 0) + 1;
  const item = {
    attempts,
    correct: (prev?.correct ?? 0) + (attempt.correct ? 1 : 0),
    lastCorrect: attempt.correct,
    lastAt: iso,
    firstCorrectAttempt: prev?.firstCorrectAttempt ?? (attempt.correct ? attempts : null),
    hintsUsed: prev?.hintsUsed ?? 0,
    solutionViewed: prev?.solutionViewed ?? false,
  };
  const history = [...p.history, { gid: attempt.gid, correct: attempt.correct, at: iso, context: attempt.context }];
  return stamp({ ...p, items: { ...p.items, [attempt.gid]: item }, history: history.slice(-HISTORY_LIMIT) }, now);
}

export function recordHint(p: Progress, gid: string, now: Date): Progress {
  const prev = p.items[gid];
  const base = prev ?? {
    attempts: 0,
    correct: 0,
    lastCorrect: false,
    lastAt: now.toISOString(),
    firstCorrectAttempt: null,
    hintsUsed: 0,
    solutionViewed: false,
  };
  return stamp({ ...p, items: { ...p.items, [gid]: { ...base, hintsUsed: base.hintsUsed + 1 } } }, now);
}

export function recordSolutionViewed(p: Progress, gid: string, now: Date): Progress {
  const prev = p.items[gid];
  const base = prev ?? {
    attempts: 0,
    correct: 0,
    lastCorrect: false,
    lastAt: now.toISOString(),
    firstCorrectAttempt: null,
    hintsUsed: 0,
    solutionViewed: false,
  };
  return stamp({ ...p, items: { ...p.items, [gid]: { ...base, solutionViewed: true } } }, now);
}

export function saveCode(p: Progress, key: string, code: string, now: Date): Progress {
  if (p.code[key]?.code === code) return p;
  return stamp({ ...p, code: { ...p.code, [key]: { code, updatedAt: now.toISOString() } } }, now);
}

export function clearCode(p: Progress, key: string, now: Date): Progress {
  if (!p.code[key]) return p;
  const code = { ...p.code };
  delete code[key];
  return stamp({ ...p, code }, now);
}

export function completeMasteryCheck(p: Progress, args: { conceptId: string; lessonId: string; score: number; passed: boolean }, now: Date): Progress {
  const iso = now.toISOString();
  let next = withConcept(p, args.conceptId, (c) => ({
    ...c,
    lastMasteryAttemptAt: iso,
    masteryScore: args.score,
    masteredAt: args.passed ? (c.masteredAt ?? iso) : c.masteredAt,
    review: args.passed ? (c.review ? nextReview(c.review, true, now) : initialReview(now)) : c.review,
  }));
  if (args.passed && next.lessons[args.lessonId]) {
    const lesson = next.lessons[args.lessonId]!;
    next = { ...next, lessons: { ...next.lessons, [args.lessonId]: { ...lesson, completedAt: lesson.completedAt ?? iso } } };
  }
  return stamp(next, now);
}

export function completeReview(p: Progress, conceptId: string, passed: boolean, now: Date): Progress {
  return stamp(
    withConcept(p, conceptId, (c) => ({ ...c, review: nextReview(c.review, passed, now) })),
    now,
  );
}

export function setDiagnostic(p: Progress, conceptId: string, value: "passed" | "self-reported" | null, now: Date): Progress {
  return stamp(
    withConcept(p, conceptId, (c) => ({
      ...c,
      diagnostic: value,
      review: value === "passed" && !c.review ? initialReview(now) : c.review,
    })),
    now,
  );
}

export function updateSettings(p: Progress, patch: Partial<Settings>, now: Date): Progress {
  return stamp({ ...p, settings: { ...p.settings, ...patch } }, now);
}

export function saveSnippet(p: Progress, snippet: { id: string; title: string; code: string }, now: Date): Progress {
  const iso = now.toISOString();
  const existing = p.snippets.find((s) => s.id === snippet.id);
  const snippets = existing
    ? p.snippets.map((s) => (s.id === snippet.id ? { ...s, title: snippet.title, code: snippet.code, updatedAt: iso } : s))
    : [...p.snippets, { ...snippet, createdAt: iso, updatedAt: iso }];
  return stamp({ ...p, snippets }, now);
}

export function deleteSnippet(p: Progress, id: string, now: Date): Progress {
  return stamp({ ...p, snippets: p.snippets.filter((s) => s.id !== id) }, now);
}

export function setMilestone(p: Progress, projectId: string, milestoneId: string, done: boolean, method: "tests" | "self", now: Date): Progress {
  const iso = now.toISOString();
  const project = p.projects[projectId] ?? { startedAt: iso, milestones: {}, rubric: {} };
  const milestones = { ...project.milestones };
  if (done) milestones[milestoneId] = { doneAt: milestones[milestoneId]?.doneAt ?? iso, method };
  else delete milestones[milestoneId];
  return stamp({ ...p, projects: { ...p.projects, [projectId]: { ...project, milestones } } }, now);
}

export function setRubric(p: Progress, projectId: string, criterion: string, level: "needsWork" | "meets" | "exceeds", now: Date): Progress {
  const iso = now.toISOString();
  const project = p.projects[projectId] ?? { startedAt: iso, milestones: {}, rubric: {} };
  return stamp({ ...p, projects: { ...p.projects, [projectId]: { ...project, rubric: { ...project.rubric, [criterion]: level } } } }, now);
}

export function rateInterviewQuestion(p: Progress, questionId: string, rating: "missed" | "partial" | "solid", now: Date): Progress {
  const prev = p.interview[questionId];
  const streak = rating === "solid" ? (prev?.rating === "solid" ? prev.streak + 1 : 1) : 0;
  const dueAt = addDays(now, interviewInterval(rating, streak)).toISOString();
  return stamp({ ...p, interview: { ...p.interview, [questionId]: { rating, at: now.toISOString(), dueAt, streak } } }, now);
}
