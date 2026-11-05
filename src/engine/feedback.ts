// Exercise feedback: deterministic misconception rules authored in lesson YAML.
import type { FeedbackRule } from "../content/schema";
import type { RunResult } from "../python/types";
import { normalizeOutput } from "./output";

export function matchesRule(rule: FeedbackRule, run: RunResult, code: string): boolean {
  const w = rule.when;
  const checks: boolean[] = [];
  if (w.outputEquals !== undefined) checks.push(normalizeOutput(run.stdout) === normalizeOutput(w.outputEquals));
  if (w.outputContains !== undefined) checks.push(run.stdout.includes(w.outputContains));
  if (w.errorType !== undefined) checks.push(run.error?.type === w.errorType);
  if (w.errorMessageContains !== undefined) checks.push(Boolean(run.error?.message.includes(w.errorMessageContains)));
  if (w.codeContains !== undefined) checks.push(code.includes(w.codeContains));
  if (w.codeMatches !== undefined) {
    try {
      checks.push(new RegExp(w.codeMatches, "m").test(code));
    } catch {
      checks.push(false);
    }
  }
  return checks.length > 0 && checks.every(Boolean);
}

/** All matching messages, in authoring order. */
export function feedbackFor(rules: FeedbackRule[], run: RunResult, code: string): string[] {
  return rules.filter((r) => matchesRule(r, run, code)).map((r) => r.message);
}

/** Compare a predicted output with the answer; returns targeted feedback for known wrong answers. */
export function gradePrediction(
  answer: string,
  expected: string,
  wrongAnswers: { answer: string; feedback: string }[],
): { correct: boolean; feedback: string | null } {
  const given = normalizeOutput(answer);
  if (given === normalizeOutput(expected)) return { correct: true, feedback: null };
  // Tolerate the most common formatting slip: extra spaces between values.
  if (given.replace(/[ \t]+/g, " ") === normalizeOutput(expected).replace(/[ \t]+/g, " ")) {
    return { correct: true, feedback: "Correct (watch the spacing: print puts exactly one space between values)." };
  }
  const known = wrongAnswers.find((w) => normalizeOutput(w.answer) === given);
  return { correct: false, feedback: known?.feedback ?? null };
}
