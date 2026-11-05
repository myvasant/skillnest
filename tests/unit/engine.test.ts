import { describe, expect, it } from "vitest";
import { conceptMastery, scoreMasteryCheck } from "../../src/engine/mastery";
import { recommend } from "../../src/engine/recommend";
import { DAY_MS, initialReview, interviewInterval, isDue, nextReview } from "../../src/engine/review";
import { completeMasteryCheck, completeReview, recordAttempt, seeSection, setDiagnostic, visitLesson } from "../../src/storage/actions";
import { emptyProgress, type Progress } from "../../src/storage/progress";
import { smallCurriculum } from "../helpers/fixtures";

const T0 = new Date("2026-10-22T10:00:00Z");
const at = (days: number) => new Date(T0.getTime() + days * DAY_MS);
const { index } = smallCurriculum();

function answer(p: Progress, gid: string, correct: boolean, when = T0): Progress {
  return recordAttempt(p, { gid, correct, context: "practice" }, when);
}

describe("review schedule", () => {
  it("starts at box 1, due after one day", () => {
    const r = initialReview(T0);
    expect(r.box).toBe(1);
    expect(new Date(r.dueAt).getTime() - T0.getTime()).toBe(DAY_MS);
  });
  it("moves up a box on success and resets to due-now on failure", () => {
    const r1 = initialReview(T0);
    const r2 = nextReview(r1, true, at(1));
    expect(r2.box).toBe(2);
    expect(new Date(r2.dueAt).getTime()).toBe(at(1 + 3).getTime());
    const r3 = nextReview(r2, false, at(4));
    expect(r3).toMatchObject({ box: 1, lapses: 1 });
    expect(isDue(r3, at(4))).toBe(true);
  });
  it("caps at the last box", () => {
    let r = initialReview(T0);
    for (let i = 0; i < 10; i++) r = nextReview(r, true, T0);
    expect(r.box).toBe(6);
  });
  it("interview intervals grow with a solid streak", () => {
    expect(interviewInterval("missed", 0)).toBe(1);
    expect(interviewInterval("partial", 0)).toBe(3);
    expect(interviewInterval("solid", 1)).toBe(7);
    expect(interviewInterval("solid", 3)).toBe(28);
  });
});

describe("mastery rules", () => {
  it("is not-started with no activity, learning after a visit", () => {
    let p = emptyProgress(T0);
    expect(conceptMastery("a", index, p, T0).status).toBe("not-started");
    p = visitLesson(p, "la", "Lesson la", "/learn/la", T0);
    expect(conceptMastery("a", index, p, T0).status).toBe("learning");
  });

  it("becomes proficient with >= 3 items, >= 70% latest-correct, >= 2 skills", () => {
    let p = emptyProgress(T0);
    p = answer(p, "la/q1", true);
    p = answer(p, "la/q2", true);
    expect(conceptMastery("a", index, p, T0).status).toBe("learning");
    p = answer(p, "la/q3", true);
    expect(conceptMastery("a", index, p, T0).status).toBe("proficient");
  });

  it("uses the latest attempt per item, not the best", () => {
    let p = emptyProgress(T0);
    for (const gid of ["la/q1", "la/q2", "la/q3"]) p = answer(p, gid, true);
    p = answer(p, "la/q2", false);
    p = answer(p, "la/q3", false);
    const m = conceptMastery("a", index, p, T0);
    expect(m.accuracy).toBeCloseTo(1 / 3);
    expect(m.status).toBe("learning");
  });

  it("flags weak concepts from recent history", () => {
    let p = emptyProgress(T0);
    p = answer(p, "la/q1", false);
    p = answer(p, "la/q2", false);
    p = answer(p, "la/q3", true);
    expect(conceptMastery("a", index, p, T0).weak).toBe(true);
    p = answer(p, "la/q1", true);
    p = answer(p, "la/q2", true);
    expect(conceptMastery("a", index, p, T0).weak).toBe(false);
  });

  it("is mastered after passing the mastery check, with a review scheduled", () => {
    let p = visitLesson(emptyProgress(T0), "la", "L", "/learn/la", T0);
    p = completeMasteryCheck(p, { conceptId: "a", lessonId: "la", score: 1, passed: true }, T0);
    const m = conceptMastery("a", index, p, T0);
    expect(m).toMatchObject({ status: "mastered", source: "mastery-check", reviewDue: false });
    expect(p.lessons.la!.completedAt).toBe(T0.toISOString());
    expect(conceptMastery("a", index, p, at(1)).reviewDue).toBe(true);
  });

  it("a failed mastery check records the score but does not master", () => {
    const p = completeMasteryCheck(emptyProgress(T0), { conceptId: "a", lessonId: "la", score: 0.4, passed: false }, T0);
    expect(p.concepts.a).toMatchObject({ masteredAt: null, masteryScore: 0.4, review: null });
  });

  it("diagnostics count as mastered and are labelled", () => {
    const p = setDiagnostic(emptyProgress(T0), "c", "self-reported", T0);
    expect(conceptMastery("c", index, p, T0)).toMatchObject({ status: "mastered", source: "self-reported" });
  });

  it("scores mastery checks: threshold AND an implementation item solved", () => {
    const all = [
      { gid: "la/q1", correct: true },
      { gid: "la/q2", correct: true },
      { gid: "la/q3", correct: true },
    ];
    expect(scoreMasteryCheck(all, index, 0.8).passed).toBe(true);
    const noCode = all.map((r) => (r.gid === "la/q3" ? { ...r, correct: false } : r));
    const r = scoreMasteryCheck(noCode, index, 0.6);
    expect(r.score).toBeCloseTo(2 / 3);
    expect(r.passed).toBe(false);
    expect(r.reason).toMatch(/coding or debugging/);
  });
});

describe("recommendations", () => {
  it("recommends the first concept of the path for a new learner", () => {
    const r = recommend(index, emptyProgress(T0), T0);
    expect(r.primary).toMatchObject({ kind: "next", conceptId: "a", url: "/learn/la" });
  });

  it("continues a started lesson at the last section", () => {
    let p = visitLesson(emptyProgress(T0), "la", "L", "/learn/la", T0);
    p = seeSection(p, "la", "intro", "L — Intro", T0);
    const r = recommend(index, p, T0);
    expect(r.primary.kind).toBe("mastery-check");
  });

  it("moves to the next concept after mastery, explaining the prerequisite", () => {
    const p = completeMasteryCheck(visitLesson(emptyProgress(T0), "la", "L", "/learn/la", T0), { conceptId: "a", lessonId: "la", score: 1, passed: true }, T0);
    const r = recommend(index, p, T0);
    expect(r.primary).toMatchObject({ kind: "next", conceptId: "b" });
    expect(r.primary.reason).toMatch(/Concept a/);
  });

  it("puts due reviews first", () => {
    let p = completeMasteryCheck(emptyProgress(T0), { conceptId: "a", lessonId: "la", score: 1, passed: true }, T0);
    p = completeMasteryCheck(p, { conceptId: "b", lessonId: "lb", score: 1, passed: true }, T0);
    const r = recommend(index, p, at(2));
    expect(r.primary).toMatchObject({ kind: "review" });
    expect(r.primary.reason).toMatch(/overdue/);
  });

  it("recommends an unmet prerequisite when the learner jumped ahead", () => {
    const p = completeReview(setDiagnostic(emptyProgress(T0), "d", "passed", T0), "d", true, T0);
    // Started lesson b without mastering a.
    const r = recommend(index, visitLesson(p, "lb", "Lb", "/learn/lb", T0), T0);
    expect(r.primary).toMatchObject({ kind: "continue", conceptId: "b" });
    expect(r.gaps).toEqual([{ conceptId: "a", neededBy: "b", hasLesson: true }]);
  });

  it("reports done when everything available is mastered", () => {
    let p = emptyProgress(T0);
    for (const [c, l] of [
      ["a", "la"],
      ["b", "lb"],
      ["d", "ld"],
    ] as const)
      p = completeMasteryCheck(p, { conceptId: c, lessonId: l, score: 1, passed: true }, T0);
    expect(recommend(index, p, T0).primary.kind).toBe("done");
  });
});
