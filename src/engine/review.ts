// Spaced review: a transparent Leitner-box schedule.
// Passing a mastery check puts a concept in box 1 (review after 1 day).
// Each successful review moves it up a box; a failed review sends it back to box 1, due now.
import type { ReviewState } from "../storage/progress";

export const REVIEW_INTERVAL_DAYS = [1, 3, 7, 16, 35, 90] as const;
export const DAY_MS = 24 * 60 * 60 * 1000;

export function addDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}

export function intervalForBox(box: number): number {
  const index = Math.min(Math.max(box, 1), REVIEW_INTERVAL_DAYS.length) - 1;
  return REVIEW_INTERVAL_DAYS[index]!;
}

export function initialReview(now: Date): ReviewState {
  return { box: 1, dueAt: addDays(now, intervalForBox(1)).toISOString(), lastReviewedAt: null, lapses: 0 };
}

export function nextReview(current: ReviewState | null, passed: boolean, now: Date): ReviewState {
  if (!current) return initialReview(now);
  if (passed) {
    const box = Math.min(current.box + 1, REVIEW_INTERVAL_DAYS.length);
    return { box, dueAt: addDays(now, intervalForBox(box)).toISOString(), lastReviewedAt: now.toISOString(), lapses: current.lapses };
  }
  return { box: 1, dueAt: now.toISOString(), lastReviewedAt: now.toISOString(), lapses: current.lapses + 1 };
}

export function isDue(review: ReviewState | null, now: Date): boolean {
  return review !== null && new Date(review.dueAt).getTime() <= now.getTime();
}

/** Whole days until due (negative = overdue). */
export function daysUntil(iso: string, now: Date): number {
  return Math.round((new Date(iso).getTime() - now.getTime()) / DAY_MS);
}

/** Interview-question revision: missed → 1 day, partial → 3 days, solid → 7 days doubling with each streak. */
export function interviewInterval(rating: "missed" | "partial" | "solid", streak: number): number {
  if (rating === "missed") return 1;
  if (rating === "partial") return 3;
  return Math.min(7 * 2 ** Math.max(streak - 1, 0), 120);
}
