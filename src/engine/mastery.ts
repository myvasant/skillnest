// Deterministic mastery rules (documented in CURRICULUM.md → "How mastery is measured").
//
//   not-started  no lesson visit and no attempts
//   learning     some activity, not yet proficient
//   proficient   >= 3 distinct items attempted, >= 70% correct on their latest attempt,
//                and correct answers covering >= 2 different skills
//   mastered     passed the lesson's mastery check, or passed a diagnostic, or
//                self-reported as known (shown separately as "self-reported")
//
// Flags (independent of status):
//   weak         >= 3 recent attempts on the concept and < 60% of the last 5 correct
//   reviewDue    a spaced review is due (see review.ts)
import type { CurriculumIndex } from "../content/build";
import type { Skill } from "../content/schema";
import type { Progress } from "../storage/progress";
import { isDue } from "./review";

export type MasteryStatus = "not-started" | "learning" | "proficient" | "mastered";

export interface SkillEvidence {
  skill: Skill;
  attempted: number;
  correct: number;
}

export interface ConceptMastery {
  conceptId: string;
  status: MasteryStatus;
  source: "mastery-check" | "diagnostic" | "self-reported" | null;
  hasLesson: boolean;
  itemsTotal: number;
  itemsAttempted: number;
  accuracy: number | null;
  recentAccuracy: number | null;
  skills: SkillEvidence[];
  weak: boolean;
  reviewDue: boolean;
  reviewDueAt: string | null;
  lessonProgress: number;
  masteryScore: number | null;
}

export const PROFICIENT_MIN_ITEMS = 3;
export const PROFICIENT_ACCURACY = 0.7;
export const WEAK_WINDOW = 5;
export const WEAK_MIN_ATTEMPTS = 3;
export const WEAK_ACCURACY = 0.6;

export function conceptMastery(conceptId: string, index: CurriculumIndex, progress: Progress, now: Date): ConceptMastery {
  const concept = index.concepts[conceptId];
  const itemIds = concept?.itemIds ?? [];
  const cp = progress.concepts[conceptId];
  const lessonId = concept?.lessonId ?? null;
  const lessonMeta = lessonId ? index.lessons[lessonId] : undefined;
  const lessonState = lessonId ? progress.lessons[lessonId] : undefined;

  const skillMap = new Map<Skill, SkillEvidence>();
  let attempted = 0;
  let correct = 0;
  for (const gid of itemIds) {
    const state = progress.items[gid];
    const meta = index.items[gid];
    if (!state || !meta || state.attempts === 0) continue;
    attempted += 1;
    const evidence = skillMap.get(meta.skill) ?? { skill: meta.skill, attempted: 0, correct: 0 };
    evidence.attempted += 1;
    if (state.lastCorrect) {
      correct += 1;
      evidence.correct += 1;
    }
    skillMap.set(meta.skill, evidence);
  }
  const itemSet = new Set(itemIds);
  const recent = progress.history.filter((h) => itemSet.has(h.gid)).slice(-WEAK_WINDOW);
  const recentAccuracy = recent.length ? recent.filter((h) => h.correct).length / recent.length : null;
  const accuracy = attempted ? correct / attempted : null;
  const skills = [...skillMap.values()];
  const correctSkills = skills.filter((s) => s.correct > 0).length;

  let status: MasteryStatus = "not-started";
  let source: ConceptMastery["source"] = null;
  if (cp?.masteredAt) {
    status = "mastered";
    source = "mastery-check";
  } else if (cp?.diagnostic) {
    status = "mastered";
    source = cp.diagnostic === "passed" ? "diagnostic" : "self-reported";
  } else if (attempted >= PROFICIENT_MIN_ITEMS && (accuracy ?? 0) >= PROFICIENT_ACCURACY && correctSkills >= 2) {
    status = "proficient";
  } else if (attempted > 0 || lessonState) {
    status = "learning";
  }

  const sectionTotal = lessonMeta?.sections.length ?? 0;
  const lessonProgress = sectionTotal && lessonState ? Math.min(1, lessonState.sectionsSeen.length / sectionTotal) : 0;
  const review = cp?.review ?? null;

  return {
    conceptId,
    status,
    source,
    hasLesson: Boolean(lessonId),
    itemsTotal: itemIds.length,
    itemsAttempted: attempted,
    accuracy,
    recentAccuracy,
    skills,
    weak: recent.length >= WEAK_MIN_ATTEMPTS && (recentAccuracy ?? 1) < WEAK_ACCURACY,
    reviewDue: isDue(review, now),
    reviewDueAt: review?.dueAt ?? null,
    lessonProgress,
    masteryScore: cp?.masteryScore ?? null,
  };
}

/** A prerequisite counts as satisfied when mastered/proficient, or when it has no lesson yet (outline-only). */
export function isSatisfied(m: ConceptMastery): boolean {
  return m.status === "mastered" || m.status === "proficient";
}

export function allMastery(index: CurriculumIndex, progress: Progress, now: Date): Record<string, ConceptMastery> {
  const out: Record<string, ConceptMastery> = {};
  for (const id of index.conceptOrder) out[id] = conceptMastery(id, index, progress, now);
  return out;
}

export interface MasteryCheckResult {
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  /** True when the check contained a code/debug item and at least one was solved. */
  implementationShown: boolean;
  reason: string;
}

/** Pass = score >= threshold AND (if the check contains code/debug items) at least one of them correct. */
export function scoreMasteryCheck(results: { gid: string; correct: boolean }[], index: CurriculumIndex, threshold: number): MasteryCheckResult {
  const total = results.length;
  const correct = results.filter((r) => r.correct).length;
  const score = total ? correct / total : 0;
  const codeItems = results.filter((r) => {
    const type = index.items[r.gid]?.type;
    return type === "code" || type === "debug";
  });
  const implementationShown = codeItems.length === 0 || codeItems.some((r) => r.correct);
  const passed = score >= threshold && implementationShown;
  let reason: string;
  if (passed) reason = `You answered ${correct} of ${total} correctly (needed ${Math.ceil(threshold * total)}).`;
  else if (score >= threshold) reason = "Your score was high enough, but mastery also needs at least one coding or debugging task solved independently.";
  else reason = `You answered ${correct} of ${total} correctly; ${Math.ceil(threshold * total)} are needed.`;
  return { score, passed, correct, total, implementationShown, reason };
}
