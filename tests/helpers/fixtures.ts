// Small synthetic curricula for unit tests (independent of real content).
import { compileContent, type RawContent } from "../../src/content/build";

export function concept(id: string, requires: string[] = [], extra: Record<string, unknown> = {}) {
  return { id, title: `Concept ${id}`, module: "m", level: "beginner", priority: "essential", summary: `Summary of ${id} for tests.`, requires, ...extra };
}

export function stage(concepts: ReturnType<typeof concept>[], extra: Record<string, unknown> = {}) {
  return {
    id: "s",
    order: 1,
    title: "Stage",
    shortTitle: "S",
    summary: "A test stage.",
    why: "Because tests.",
    modules: [{ id: "m", title: "Module", summary: "Test module." }],
    concepts,
    ...extra,
  };
}

export function lesson(id: string, conceptId: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    concept: conceptId,
    title: `Lesson ${id}`,
    estimatedMinutes: 10,
    summary: "A lesson used in tests.",
    objectives: ["Pass tests"],
    sources: [{ title: "Python docs", url: "https://docs.python.org/3/" }],
    reviewedOn: "2026-10-22",
    sections: [
      {
        id: "intro",
        title: "Intro",
        blocks: [
          { type: "markdown", body: "Hello" },
          { type: "item", ref: "q1" },
        ],
      },
    ],
    items: [
      { id: "q1", type: "true-false", skill: "recognition", prompt: "Is this a test?", explanation: "It is a test.", answer: true },
      { id: "q2", type: "predict-output", skill: "prediction", prompt: "What prints?", explanation: "It prints 1.", code: "print(1)", answer: "1" },
      {
        id: "q3",
        type: "code",
        skill: "implementation",
        prompt: "Print 2 please.",
        explanation: "print(2) prints 2.",
        starterCode: "",
        solution: "print(2)",
        tests: [{ name: "prints 2", code: "assert output() == '2\\n'" }],
        hints: ["Use print."],
      },
    ],
    masteryCheck: { items: ["q1", "q2", "q3"] },
    ...extra,
  };
}

export function raw(parts: Partial<RawContent> & { stageData?: unknown[]; lessonData?: unknown[] } = {}): RawContent {
  return {
    stages: (parts.stageData ?? []).map((data, i) => ({ file: `stages/${i}.yaml`, data })),
    lessons: (parts.lessonData ?? []).map((data, i) => ({ file: `lessons/${i}.yaml`, data })),
    glossary: parts.glossary ?? [],
    paths: parts.paths ?? null,
    projects: parts.projects ?? [],
    interview: parts.interview ?? [],
  };
}

/** A tiny valid curriculum: a → b → c, lessons for a and b, one path targeting c. */
export function smallCurriculum() {
  return compileContent(
    raw({
      stageData: [stage([concept("a"), concept("b", ["a"]), concept("c", ["b"]), concept("d", ["a"])])],
      lessonData: [lesson("la", "a"), lesson("lb", "b"), lesson("ld", "d")],
      paths: {
        file: "paths.yaml",
        data: { defaultPath: "p", paths: [{ id: "p", title: "P", role: "Tester", summary: "Test path.", outcomes: ["x"], targets: ["c", "d"] }] },
      },
    }),
  );
}
