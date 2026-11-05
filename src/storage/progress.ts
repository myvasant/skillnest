// The learner's progress: a single versioned JSON document stored in
// localStorage, validated on load and on import. Nothing leaves the device.
import { z } from "zod";

export const PROGRESS_STORAGE_KEY = "groundwork:progress";
export const PROGRESS_SCHEMA_VERSION = 1;
export const EXPORT_FORMAT = "groundwork-progress";
export const HISTORY_LIMIT = 2000;

const IsoDate = z.string().min(10);

export const AttemptContextSchema = z.enum(["practice", "mastery", "review", "diagnostic"]);

const SettingsSchema = z.object({
  theme: z.enum(["system", "light", "dark"]).default("system"),
  motion: z.enum(["system", "reduce"]).default("system"),
  editorFontSize: z.number().int().min(11).max(22).default(14),
  showDeepDives: z.boolean().default(false),
  activePath: z.string().nullable().default(null),
});

const LessonProgressSchema = z.object({
  startedAt: IsoDate,
  lastVisitedAt: IsoDate,
  lastSection: z.string().nullable().default(null),
  sectionsSeen: z.array(z.string()).default([]),
  completedAt: IsoDate.nullable().default(null),
});

const ItemProgressSchema = z.object({
  attempts: z.number().int().nonnegative(),
  correct: z.number().int().nonnegative(),
  lastCorrect: z.boolean(),
  lastAt: IsoDate,
  firstCorrectAttempt: z.number().int().positive().nullable().default(null),
  hintsUsed: z.number().int().nonnegative().default(0),
  solutionViewed: z.boolean().default(false),
});

const HistoryEntrySchema = z.object({
  gid: z.string(),
  correct: z.boolean(),
  at: IsoDate,
  context: AttemptContextSchema,
});

const ReviewStateSchema = z.object({
  box: z.number().int().min(1).max(6),
  dueAt: IsoDate,
  lastReviewedAt: IsoDate.nullable().default(null),
  lapses: z.number().int().nonnegative().default(0),
});

const ConceptProgressSchema = z.object({
  masteredAt: IsoDate.nullable().default(null),
  masteryScore: z.number().min(0).max(1).nullable().default(null),
  lastMasteryAttemptAt: IsoDate.nullable().default(null),
  diagnostic: z.enum(["passed", "self-reported"]).nullable().default(null),
  review: ReviewStateSchema.nullable().default(null),
});

const SnippetSchema = z.object({
  id: z.string(),
  title: z.string().max(120),
  code: z.string().max(100_000),
  createdAt: IsoDate,
  updatedAt: IsoDate,
});

const ProjectProgressSchema = z.object({
  startedAt: IsoDate,
  milestones: z.record(z.string(), z.object({ doneAt: IsoDate, method: z.enum(["tests", "self"]) })).default({}),
  rubric: z.record(z.string(), z.enum(["needsWork", "meets", "exceeds"])).default({}),
});

const InterviewProgressSchema = z.object({
  rating: z.enum(["missed", "partial", "solid"]),
  at: IsoDate,
  dueAt: IsoDate,
  streak: z.number().int().nonnegative().default(0),
});

export const ProgressSchema = z.object({
  schemaVersion: z.literal(PROGRESS_SCHEMA_VERSION),
  createdAt: IsoDate,
  updatedAt: IsoDate,
  settings: SettingsSchema.default(SettingsSchema.parse({})),
  lessons: z.record(z.string(), LessonProgressSchema).default({}),
  items: z.record(z.string(), ItemProgressSchema).default({}),
  history: z.array(HistoryEntrySchema).default([]),
  concepts: z.record(z.string(), ConceptProgressSchema).default({}),
  code: z.record(z.string(), z.object({ code: z.string().max(100_000), updatedAt: IsoDate })).default({}),
  snippets: z.array(SnippetSchema).default([]),
  projects: z.record(z.string(), ProjectProgressSchema).default({}),
  interview: z.record(z.string(), InterviewProgressSchema).default({}),
  lastLocation: z.object({ path: z.string(), title: z.string(), at: IsoDate }).nullable().default(null),
});

export type Progress = z.infer<typeof ProgressSchema>;
export type Settings = z.infer<typeof SettingsSchema>;
export type ItemProgress = z.infer<typeof ItemProgressSchema>;
export type ConceptProgress = z.infer<typeof ConceptProgressSchema>;
export type ReviewState = z.infer<typeof ReviewStateSchema>;
export type AttemptContext = z.infer<typeof AttemptContextSchema>;
export type HistoryEntry = z.infer<typeof HistoryEntrySchema>;
export type Snippet = z.infer<typeof SnippetSchema>;
export type InterviewProgress = z.infer<typeof InterviewProgressSchema>;

export function emptyProgress(now: Date = new Date()): Progress {
  const iso = now.toISOString();
  return ProgressSchema.parse({ schemaVersion: PROGRESS_SCHEMA_VERSION, createdAt: iso, updatedAt: iso });
}

export const emptyConceptProgress = (): ConceptProgress => ConceptProgressSchema.parse({});

/**
 * Upgrade older documents to the current schema. Version 1 is the first
 * release, so this only rejects unknown future versions; add steps here when
 * the schema changes (never mutate the meaning of an existing version).
 */
export function migrate(raw: unknown): unknown {
  if (!raw || typeof raw !== "object") throw new Error("Progress data is not an object.");
  const version = (raw as { schemaVersion?: unknown }).schemaVersion;
  if (version === PROGRESS_SCHEMA_VERSION) return raw;
  if (typeof version === "number" && version > PROGRESS_SCHEMA_VERSION) {
    throw new Error(`This progress file was made by a newer version of Groundwork (schema v${version}). Update the app to import it.`);
  }
  throw new Error(`Unrecognised progress schema version: ${String(version)}`);
}

export type ParseResult = { ok: true; progress: Progress } | { ok: false; error: string };

export function parseProgress(raw: unknown): ParseResult {
  try {
    const parsed = ProgressSchema.safeParse(migrate(raw));
    if (!parsed.success) {
      const first = parsed.error.issues[0];
      return { ok: false, error: `Invalid progress data at "${first?.path.join(".") || "(root)"}": ${first?.message ?? "unknown problem"}` };
    }
    return { ok: true, progress: parsed.data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

// ---------------------------------------------------------------------------
// Export / import
// ---------------------------------------------------------------------------

export interface ExportFile {
  format: typeof EXPORT_FORMAT;
  exportedAt: string;
  appVersion: string;
  progress: Progress;
}

export function createExport(progress: Progress, appVersion: string, now: Date = new Date()): ExportFile {
  return { format: EXPORT_FORMAT, exportedAt: now.toISOString(), appVersion, progress };
}

export function parseExport(text: string): ParseResult & { exportedAt?: string } {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return { ok: false, error: "The file is not valid JSON." };
  }
  if (!data || typeof data !== "object" || (data as { format?: unknown }).format !== EXPORT_FORMAT) {
    return { ok: false, error: "This is not a Groundwork progress export (missing format marker)." };
  }
  const result = parseProgress((data as { progress?: unknown }).progress);
  if (!result.ok) return result;
  return { ...result, exportedAt: String((data as { exportedAt?: unknown }).exportedAt ?? "") };
}

export interface ProgressSummary {
  lessonsStarted: number;
  lessonsCompleted: number;
  conceptsMastered: number;
  itemsAttempted: number;
  snippets: number;
  projects: number;
}

export function summarizeProgress(p: Progress): ProgressSummary {
  return {
    lessonsStarted: Object.keys(p.lessons).length,
    lessonsCompleted: Object.values(p.lessons).filter((l) => l.completedAt).length,
    conceptsMastered: Object.values(p.concepts).filter((c) => c.masteredAt || c.diagnostic).length,
    itemsAttempted: Object.keys(p.items).length,
    snippets: p.snippets.length,
    projects: Object.keys(p.projects).length,
  };
}
