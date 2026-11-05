// Deterministic "what should I do next?" rules. Every recommendation carries a
// plain-English reason so the learner can see why it was chosen.
//
// Priority order:
//   1. Spaced reviews that are due (most overdue first)
//   2. Weak concepts (recent accuracy below 60%)
//   3. A started lesson whose mastery check has not been passed
//   4. The next concept in the active learning path whose lesson exists
//      (if the learner has jumped ahead, its earliest unmet prerequisite instead)
//   5. Nothing left: every available lesson in the path is mastered
import type { CurriculumIndex } from "../content/build";
import type { Progress } from "../storage/progress";
import { allMastery, isSatisfied, type ConceptMastery } from "./mastery";
import { daysUntil } from "./review";

export type RecommendationKind = "review" | "weak" | "continue" | "mastery-check" | "next" | "prerequisite" | "done";

export interface Recommendation {
  kind: RecommendationKind;
  conceptId: string | null;
  lessonId: string | null;
  title: string;
  reason: string;
  url: string;
}

export interface RecommendationSet {
  primary: Recommendation;
  others: Recommendation[];
  /** Prerequisites of active work that are not yet satisfied. */
  gaps: { conceptId: string; neededBy: string; hasLesson: boolean }[];
  pathId: string;
}

export function activePathId(index: CurriculumIndex, progress: Progress): string {
  const chosen = progress.settings.activePath;
  return chosen && index.paths.some((p) => p.id === chosen) ? chosen : index.defaultPath;
}

/** Earliest unsatisfied ancestor (with a lesson) of a concept, in curriculum order. */
export function firstUnmetPrerequisite(conceptId: string, index: CurriculumIndex, mastery: Record<string, ConceptMastery>): string | null {
  const ancestors = new Set<string>();
  const visit = (id: string) => {
    for (const r of index.concepts[id]?.requires ?? []) {
      if (!ancestors.has(r)) {
        ancestors.add(r);
        visit(r);
      }
    }
  };
  visit(conceptId);
  for (const id of index.conceptOrder) {
    if (!ancestors.has(id)) continue;
    const m = mastery[id];
    if (m && m.hasLesson && !isSatisfied(m)) return id;
  }
  return null;
}

export function recommend(index: CurriculumIndex, progress: Progress, now: Date): RecommendationSet {
  const mastery = allMastery(index, progress, now);
  const pathId = activePathId(index, progress);
  const path = index.paths.find((p) => p.id === pathId);
  const recs: Recommendation[] = [];
  const title = (id: string) => index.concepts[id]?.title ?? id;
  const lessonUrl = (lessonId: string, anchor?: string) => `/learn/${lessonId}${anchor ? `#${anchor}` : ""}`;

  // 1. Due reviews
  const due = Object.values(mastery)
    .filter((m) => m.reviewDue && m.reviewDueAt)
    .sort((a, b) => a.reviewDueAt!.localeCompare(b.reviewDueAt!));
  for (const m of due) {
    const days = -daysUntil(m.reviewDueAt!, now);
    recs.push({
      kind: "review",
      conceptId: m.conceptId,
      lessonId: index.concepts[m.conceptId]?.lessonId ?? null,
      title: `Review: ${title(m.conceptId)}`,
      reason:
        days > 0
          ? `Your spaced review is ${days} day${days === 1 ? "" : "s"} overdue. Short, spaced recall is what makes knowledge stick.`
          : "A spaced review is due today. Recalling it now, just as you start to forget, strengthens long-term memory.",
      url: `/review?concept=${m.conceptId}`,
    });
  }

  // 2. Weak concepts
  for (const m of Object.values(mastery)) {
    if (!m.weak || !m.hasLesson || m.reviewDue) continue;
    const lessonId = index.concepts[m.conceptId]!.lessonId!;
    recs.push({
      kind: "weak",
      conceptId: m.conceptId,
      lessonId,
      title: `Strengthen: ${title(m.conceptId)}`,
      reason: `Only ${Math.round((m.recentAccuracy ?? 0) * 100)}% of your recent answers on this concept were correct. Revisit the explanation and retry the practice.`,
      url: lessonUrl(lessonId, "practice"),
    });
  }

  // 3. Started but not mastered lessons (most recent first)
  const started = Object.entries(progress.lessons)
    .filter(([lessonId]) => index.lessons[lessonId])
    .sort(([, a], [, b]) => b.lastVisitedAt.localeCompare(a.lastVisitedAt));
  for (const [lessonId, state] of started) {
    const meta = index.lessons[lessonId]!;
    const m = mastery[meta.concept];
    if (!m || m.status === "mastered") continue;
    const allSeen = state.sectionsSeen.length >= meta.sections.filter((s) => s.depth === "core").length;
    if (allSeen && meta.masteryItemIds.length) {
      recs.push({
        kind: "mastery-check",
        conceptId: meta.concept,
        lessonId,
        title: `Mastery check: ${meta.title}`,
        reason: "You have worked through every section. The mastery check confirms you can predict, write and debug this on your own.",
        url: lessonUrl(lessonId, "mastery-check"),
      });
    } else {
      const section = meta.sections.find((s) => s.id === state.lastSection);
      recs.push({
        kind: "continue",
        conceptId: meta.concept,
        lessonId,
        title: `Continue: ${meta.title}`,
        reason: section ? `Pick up where you left off, at "${section.title}".` : "You started this lesson but have not finished it.",
        url: lessonUrl(lessonId, state.lastSection ?? undefined),
      });
    }
  }

  // 4. Next concept in the active path
  const gaps: RecommendationSet["gaps"] = [];
  if (path) {
    for (const conceptId of path.conceptIds) {
      const m = mastery[conceptId];
      if (!m || !m.hasLesson || isSatisfied(m)) continue;
      if (recs.some((r) => r.conceptId === conceptId)) break;
      const unmet = firstUnmetPrerequisite(conceptId, index, mastery);
      const lessonId = index.concepts[conceptId]!.lessonId!;
      if (unmet && unmet !== conceptId) {
        const unmetLesson = index.concepts[unmet]!.lessonId!;
        recs.push({
          kind: "prerequisite",
          conceptId: unmet,
          lessonId: unmetLesson,
          title: `Prerequisite: ${title(unmet)}`,
          reason: `"${title(conceptId)}" builds on "${title(unmet)}", which you have not mastered yet.`,
          url: lessonUrl(unmetLesson),
        });
      } else {
        const requires = index.concepts[conceptId]!.requires;
        recs.push({
          kind: "next",
          conceptId,
          lessonId,
          title: `Next: ${title(conceptId)}`,
          reason: requires.length
            ? `It is the next step in the ${path.title} path, and it builds on ${requires.map(title).join(", ")}.`
            : `It is the next step in the ${path.title} path.`,
          url: lessonUrl(lessonId),
        });
      }
      break;
    }
  }

  // Gaps: unmet prerequisites of lessons in progress or the next step.
  const focus = new Set(recs.filter((r) => r.conceptId && (r.kind === "continue" || r.kind === "next" || r.kind === "mastery-check")).map((r) => r.conceptId!));
  for (const conceptId of focus) {
    for (const r of index.concepts[conceptId]?.requires ?? []) {
      const m = mastery[r];
      if (m && !isSatisfied(m) && !gaps.some((g) => g.conceptId === r)) gaps.push({ conceptId: r, neededBy: conceptId, hasLesson: m.hasLesson });
    }
  }

  if (!recs.length) {
    recs.push({
      kind: "done",
      conceptId: null,
      lessonId: null,
      title: path ? `${path.title}: all available lessons mastered` : "All available lessons mastered",
      reason: "Choose another learning path, tackle a project, or practise interview questions.",
      url: "/paths",
    });
  }

  // De-duplicate by concept, keeping the highest-priority entry.
  const seen = new Set<string>();
  const unique = recs.filter((r) => {
    const key = r.conceptId ?? r.kind;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return { primary: unique[0]!, others: unique.slice(1, 5), gaps, pathId };
}
