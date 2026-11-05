// The curriculum content format. Every YAML file under content/ is validated
// against these schemas (see CONTENT_SCHEMA.md). Strict objects are used so a
// misspelled key is reported instead of silently ignored.
import { z } from "zod";

export const IdSchema = z.string().regex(/^[a-z0-9]+(?:[.-][a-z0-9]+)*$/, "ids use lowercase letters, digits, '.', and '-' (e.g. python.variables)");

export const LevelSchema = z.enum(["beginner", "intermediate", "advanced"]);
export const PrioritySchema = z.enum(["essential", "supporting", "advanced", "optional", "technology-specific"]);
export const SkillSchema = z.enum(["recognition", "explanation", "prediction", "implementation", "debugging", "transfer", "design"]);

export const SourceSchema = z.strictObject({
  title: z.string().min(3),
  url: z.url(),
  publisher: z.string().optional(),
  version: z.string().optional(),
  note: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Curriculum graph: stages -> modules -> concepts
// ---------------------------------------------------------------------------

export const ConceptSchema = z.strictObject({
  id: IdSchema,
  title: z.string().min(2),
  module: IdSchema,
  level: LevelSchema,
  priority: PrioritySchema,
  summary: z.string().min(10),
  why: z.string().optional(),
  keyIdeas: z.array(z.string()).default([]),
  misconceptions: z.array(z.string()).default([]),
  requires: z.array(IdSchema).default([]),
  extends: z.array(IdSchema).default([]),
  contrastsWith: z.array(IdSchema).default([]),
  confusedWith: z.array(IdSchema).default([]),
  tools: z.array(z.string()).default([]),
  interview: z.string().optional(),
  production: z.string().optional(),
  sources: z.array(SourceSchema).default([]),
});

export const ModuleSchema = z.strictObject({
  id: IdSchema,
  title: z.string(),
  summary: z.string(),
});

export const StageSchema = z.strictObject({
  id: IdSchema,
  order: z.number().int().positive(),
  title: z.string(),
  shortTitle: z.string(),
  summary: z.string(),
  why: z.string(),
  modules: z.array(ModuleSchema).min(1),
  concepts: z.array(ConceptSchema).min(1),
});

// ---------------------------------------------------------------------------
// Assessment items
// ---------------------------------------------------------------------------

const ItemBase = {
  id: IdSchema,
  /** Concepts this item provides evidence for. Defaults to the lesson's concept. */
  concepts: z.array(IdSchema).optional(),
  skill: SkillSchema,
  difficulty: z.union([z.literal(1), z.literal(2), z.literal(3)]).default(1),
  prompt: z.string().min(5),
  /** Shown after answering, right or wrong: the reasoning. */
  explanation: z.string().min(5),
};

export const ExerciseTestSchema = z.strictObject({
  name: z.string().min(2),
  code: z.string().min(1),
});

export const FeedbackRuleSchema = z.strictObject({
  when: z
    .strictObject({
      outputEquals: z.string().optional(),
      outputContains: z.string().optional(),
      errorType: z.string().optional(),
      errorMessageContains: z.string().optional(),
      codeContains: z.string().optional(),
      codeMatches: z.string().optional(),
    })
    .refine((w) => Object.values(w).some((v) => v !== undefined), "a feedback rule needs at least one condition"),
  message: z.string().min(5),
});

export const McqItemSchema = z.strictObject({
  ...ItemBase,
  type: z.literal("mcq"),
  options: z
    .array(
      z.strictObject({
        id: z.string().min(1),
        text: z.string().min(1),
        correct: z.boolean().default(false),
        feedback: z.string().min(3),
      }),
    )
    .min(2),
});

export const TrueFalseItemSchema = z.strictObject({
  ...ItemBase,
  type: z.literal("true-false"),
  answer: z.boolean(),
});

export const PredictItemSchema = z.strictObject({
  ...ItemBase,
  type: z.literal("predict-output"),
  code: z.string().min(1),
  /** Exact program output; also verified by running `code` in the content tests. */
  answer: z.string(),
  wrongAnswers: z.array(z.strictObject({ answer: z.string(), feedback: z.string().min(5) })).default([]),
});

export const CodeItemSchema = z.strictObject({
  ...ItemBase,
  type: z.enum(["code", "debug"]),
  starterCode: z.string(),
  solution: z.string().min(1),
  tests: z.array(ExerciseTestSchema).min(1),
  hints: z.array(z.string()).min(1),
  stdin: z.string().optional(),
  expectedOutput: z.string().optional(),
  feedback: z.array(FeedbackRuleSchema).default([]),
});

export const ExplainItemSchema = z.strictObject({
  ...ItemBase,
  type: z.literal("explain"),
  rubric: z.array(z.string().min(5)).min(2),
  modelAnswer: z.string().min(10),
});

export const ParsonsItemSchema = z.strictObject({
  ...ItemBase,
  type: z.literal("parsons"),
  /** The correct program, one statement per line (indentation preserved). */
  solution: z.string().min(1),
  distractors: z.array(z.string()).default([]),
  expectedOutput: z.string().optional(),
});

export const ItemSchema = z.discriminatedUnion("type", [
  McqItemSchema,
  TrueFalseItemSchema,
  PredictItemSchema,
  CodeItemSchema,
  ExplainItemSchema,
  ParsonsItemSchema,
]);

// ---------------------------------------------------------------------------
// Lessons
// ---------------------------------------------------------------------------

const Depth = z.enum(["core", "deep"]).default("core");

export const MarkdownBlockSchema = z.strictObject({
  type: z.literal("markdown"),
  body: z.string().min(1),
  depth: Depth,
});

export const CodeBlockSchema = z.strictObject({
  type: z.literal("code"),
  id: IdSchema.optional(),
  language: z.enum(["python", "text", "bash", "powershell", "sql", "json", "yaml", "http", "toml", "dockerfile", "javascript", "cypher"]).default("python"),
  code: z.string().min(1),
  caption: z.string().optional(),
  /** Let the learner run (and edit) it in the browser. Python only. */
  runnable: z.boolean().default(false),
  /** Exact expected stdout; verified by the content tests when present. */
  expectedOutput: z.string().optional(),
  /** If the example deliberately fails, the exception type it raises. */
  expectError: z.string().optional(),
  stdin: z.string().optional(),
  /** "verified" = executed by tests; "illustrative" = not executed (explain why in caption). */
  status: z.enum(["verified", "illustrative", "pseudocode"]).optional(),
  annotations: z.array(z.strictObject({ line: z.number().int().positive(), text: z.string() })).default([]),
  depth: Depth,
});

export const CalloutBlockSchema = z.strictObject({
  type: z.literal("callout"),
  variant: z.enum(["tip", "note", "warning", "misconception", "analogy", "deep-dive", "production", "interview"]),
  title: z.string().optional(),
  body: z.string().min(1),
  depth: Depth,
});

export const VisualizationBlockSchema = z.strictObject({
  type: z.literal("visualization"),
  component: IdSchema,
  title: z.string().optional(),
  caption: z.string().optional(),
  props: z.record(z.string(), z.unknown()).default({}),
  depth: Depth,
});

export const ItemRefBlockSchema = z.strictObject({
  type: z.literal("item"),
  ref: IdSchema,
  depth: Depth,
});

export const BlockSchema = z.discriminatedUnion("type", [
  MarkdownBlockSchema,
  CodeBlockSchema,
  CalloutBlockSchema,
  VisualizationBlockSchema,
  ItemRefBlockSchema,
]);

export const SectionSchema = z.strictObject({
  id: IdSchema,
  title: z.string(),
  kind: z
    .enum(["intro", "why", "mental-model", "concept", "walkthrough", "internals", "mistakes", "debugging", "practice", "application", "interview", "summary"])
    .default("concept"),
  depth: Depth,
  blocks: z.array(BlockSchema).min(1),
});

export const LessonSchema = z.strictObject({
  id: IdSchema,
  concept: IdSchema,
  title: z.string(),
  subtitle: z.string().optional(),
  estimatedMinutes: z.number().int().positive(),
  summary: z.string().min(10),
  objectives: z.array(z.string()).min(1),
  sources: z.array(SourceSchema).min(1),
  reviewedOn: z.iso.date(),
  sections: z.array(SectionSchema).min(1),
  items: z.array(ItemSchema).default([]),
  masteryCheck: z
    .strictObject({
      passThreshold: z.number().min(0.5).max(1).default(0.8),
      items: z.array(IdSchema).min(3),
    })
    .optional(),
  cheatsheet: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Glossary, learning paths, projects, interview questions
// ---------------------------------------------------------------------------

export const GlossaryTermSchema = z.strictObject({
  id: IdSchema,
  term: z.string(),
  aliases: z.array(z.string()).default([]),
  definition: z.string().min(10),
  concept: IdSchema.optional(),
});

export const GlossarySchema = z.strictObject({ terms: z.array(GlossaryTermSchema) });

export const PathSchema = z.strictObject({
  id: IdSchema,
  title: z.string(),
  role: z.string(),
  summary: z.string(),
  outcomes: z.array(z.string()).min(1),
  targets: z.array(IdSchema).min(1),
});

export const PathsFileSchema = z.strictObject({ defaultPath: IdSchema, paths: z.array(PathSchema).min(1) });

export const MilestoneSchema = z.strictObject({
  id: IdSchema,
  title: z.string(),
  description: z.string(),
  /** In-browser checks (Pyodide). Present only for browser-based projects. */
  tests: z.array(ExerciseTestSchema).default([]),
  starterCode: z.string().optional(),
  /** Reference solution for in-browser milestones; verified by the content tests. */
  solution: z.string().optional(),
  hints: z.array(z.string()).default([]),
});

export const ProjectSchema = z.strictObject({
  id: IdSchema,
  title: z.string(),
  track: z.enum(["python-beginner", "python-intermediate", "backend", "data-ml", "genai-rag", "agentic", "production"]),
  level: LevelSchema,
  estimatedHours: z.number().positive(),
  summary: z.string(),
  problem: z.string(),
  concepts: z.array(IdSchema).min(1),
  acceptanceCriteria: z.array(z.string()).min(2),
  architecture: z.string().optional(),
  environment: z.enum(["browser", "local"]),
  setup: z.string(),
  milestones: z.array(MilestoneSchema).min(2),
  testing: z.string(),
  security: z.array(z.string()).min(1),
  extensions: z.array(z.string()).min(1),
  rubric: z.array(z.strictObject({ criterion: z.string(), needsWork: z.string(), meets: z.string(), exceeds: z.string() })).min(2),
  starterKit: z.string().optional(),
});

export const InterviewQuestionSchema = z.strictObject({
  id: IdSchema,
  level: z.enum(["junior", "mid", "senior"]),
  kind: z.enum(["conceptual", "coding", "debugging", "design", "scenario", "sql"]),
  concepts: z.array(IdSchema).min(1),
  question: z.string().min(10),
  answer: z.string().min(20),
  keyPoints: z.array(z.string()).min(2),
  followUps: z.array(z.string()).default([]),
  pitfalls: z.array(z.string()).default([]),
});

export const InterviewFileSchema = z.strictObject({
  category: z.strictObject({ id: IdSchema, title: z.string(), summary: z.string() }),
  questions: z.array(InterviewQuestionSchema).min(1),
});

export type Source = z.infer<typeof SourceSchema>;
export type Concept = z.infer<typeof ConceptSchema>;
export type Module = z.infer<typeof ModuleSchema>;
export type Stage = z.infer<typeof StageSchema>;
export type Item = z.infer<typeof ItemSchema>;
export type McqItem = z.infer<typeof McqItemSchema>;
export type TrueFalseItem = z.infer<typeof TrueFalseItemSchema>;
export type PredictItem = z.infer<typeof PredictItemSchema>;
export type CodeItem = z.infer<typeof CodeItemSchema>;
export type ExplainItem = z.infer<typeof ExplainItemSchema>;
export type ParsonsItem = z.infer<typeof ParsonsItemSchema>;
export type FeedbackRule = z.infer<typeof FeedbackRuleSchema>;
export type Block = z.infer<typeof BlockSchema>;
export type CodeBlock = z.infer<typeof CodeBlockSchema>;
export type Section = z.infer<typeof SectionSchema>;
export type Lesson = z.infer<typeof LessonSchema>;
export type GlossaryTerm = z.infer<typeof GlossaryTermSchema>;
export type LearningPath = z.infer<typeof PathSchema>;
export type Project = z.infer<typeof ProjectSchema>;
export type Milestone = z.infer<typeof MilestoneSchema>;
export type InterviewQuestion = z.infer<typeof InterviewQuestionSchema>;
export type InterviewFile = z.infer<typeof InterviewFileSchema>;
export type Skill = z.infer<typeof SkillSchema>;
export type Level = z.infer<typeof LevelSchema>;
export type Priority = z.infer<typeof PrioritySchema>;
