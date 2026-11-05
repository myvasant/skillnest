import { progressStore } from "../../storage/store";
import { recordAttempt } from "../../storage/actions";
import type { ItemMode } from "./shared";

/** Record a practice attempt (assessment-mode attempts are recorded by the owning check). */
export function reportAnswer(gid: string, mode: ItemMode, correct: boolean, onAnswered?: (correct: boolean) => void) {
  if (mode === "practice") progressStore.update((p, now) => recordAttempt(p, { gid, correct, context: "practice" }, now));
  onAnswered?.(correct);
}
