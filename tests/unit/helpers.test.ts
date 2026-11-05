import { describe, expect, it } from "vitest";
import { explainError } from "../../src/engine/errors";
import { feedbackFor, gradePrediction, matchesRule } from "../../src/engine/feedback";
import { ancestors, layeredLayout } from "../../src/engine/layout";
import { diffOutput, normalizeOutput, outputsMatch } from "../../src/engine/output";
import { SearchIndex, tokenize } from "../../src/engine/search";
import type { RunResult } from "../../src/python/types";

const run = (over: Partial<RunResult>): RunResult => ({
  status: "completed",
  ok: true,
  stdout: "",
  stderr: "",
  events: [],
  error: null,
  exitCode: null,
  durationMs: 1,
  ...over,
});
const err = (type: string, message: string, traceback = "") => ({ type, message, line: 2, column: null, traceback });

describe("output comparison", () => {
  it("ignores trailing whitespace and CRLF", () => {
    expect(normalizeOutput("a  \r\nb\n\n")).toBe("a\nb");
    expect(outputsMatch("1\n", "1")).toBe(true);
    expect(outputsMatch("1 ", "1\n\n")).toBe(true);
    expect(outputsMatch("1", "2")).toBe(false);
  });
  it("produces a line diff", () => {
    expect(diffOutput("a\nX", "a\nb\nc").map((d) => d.kind)).toEqual(["same", "changed", "missing"]);
  });
});

describe("prediction grading", () => {
  it("accepts exact answers and tolerates extra spaces between values", () => {
    expect(gradePrediction("20 10", "20 10\n", []).correct).toBe(true);
    expect(gradePrediction("20  10", "20 10", [])).toMatchObject({ correct: true, feedback: expect.stringMatching(/spacing/) });
  });
  it("returns targeted feedback for known wrong answers", () => {
    expect(gradePrediction("20 20", "20 10", [{ answer: "20 20", feedback: "Linked variables misconception." }])).toEqual({
      correct: false,
      feedback: "Linked variables misconception.",
    });
    expect(gradePrediction("7", "20 10", []).feedback).toBeNull();
  });
});

describe("feedback rules", () => {
  it("requires every condition in a rule to match", () => {
    const r = run({ stdout: "total\n" });
    expect(matchesRule({ when: { outputEquals: "total" }, message: "quotes" }, r, "")).toBe(true);
    expect(matchesRule({ when: { outputEquals: "total", codeContains: "zzz" }, message: "x" }, r, "print('total')")).toBe(false);
    expect(feedbackFor([{ when: { errorType: "NameError" }, message: "name!" }], run({ ok: false, error: err("NameError", "x") }), "")).toEqual(["name!"]);
  });
  it("treats an invalid regex as non-matching instead of crashing", () => {
    expect(matchesRule({ when: { codeMatches: "(" }, message: "x" }, run({}), "code")).toBe(false);
  });
});

describe("error explanations", () => {
  it("explains NameError and surfaces Python's suggestion", () => {
    const e = explainError(err("NameError", "name 'pritn' is not defined", "NameError: name 'pritn' is not defined. Did you mean: 'print'?"));
    expect(e.title).toMatch(/pritn/);
    expect(e.fixes[0]).toMatch(/print/);
    expect(e.learnMore?.conceptId).toBe("python.variables");
  });
  it("matches specific TypeError messages", () => {
    expect(explainError(err("TypeError", 'can only concatenate str (not "int") to str')).title).toMatch(/text and numbers/);
    expect(explainError(err("TypeError", "'str' object is not callable")).title).toMatch(/call a str/);
  });
  it("falls back to the general explanation for the type, then to a generic one", () => {
    expect(explainError(err("SyntaxError", "something odd")).title).toMatch(/couldn't read/);
    expect(explainError(err("WeirdError", "boom")).title).toBe("WeirdError");
  });
});

describe("search", () => {
  const index = new SearchIndex([
    { id: "lesson:v", kind: "lesson", title: "Variables and Assignment", text: "names bound to objects NameError", url: "/learn/v" },
    { id: "glossary:var", kind: "glossary", title: "Variable", text: "a name that refers to an object", url: "/glossary#var" },
    { id: "concept:loops", kind: "concept", title: "For loops", text: "iterate over items with range", url: "/concept/loops" },
  ]);
  it("tokenizes and strips accents", () => {
    expect(tokenize("Café, NameError!")).toEqual(["cafe", "nameerror"]);
  });
  it("ranks title matches first and supports prefix search", () => {
    expect(index.search("variab").map((h) => h.doc.id)).toEqual(["lesson:v", "glossary:var"]);
    expect(index.search("variable")[0]!.doc.id).toBe("glossary:var");
    expect(index.search("variables")[0]!.doc.id).toBe("lesson:v");
    expect(index.search("nameerr").map((h) => h.doc.id)).toEqual(["lesson:v"]);
  });
  it("requires every word to match", () => {
    expect(index.search("loops objects")).toEqual([]);
    expect(index.search("")).toEqual([]);
  });
});

describe("graph layout", () => {
  it("places prerequisites in earlier layers", () => {
    const l = layeredLayout({
      ids: ["a", "b", "c", "x"],
      edges: [
        ["a", "b"],
        ["b", "c"],
        ["a", "c"],
        ["outside", "x"],
      ],
    });
    expect([l.nodes.a!.layer, l.nodes.b!.layer, l.nodes.c!.layer, l.nodes.x!.layer]).toEqual([0, 1, 2, 0]);
    expect(l.edges).toHaveLength(3);
    expect(l.nodes.b!.x).toBeGreaterThan(l.nodes.a!.x);
  });
  it("collects transitive ancestors", () => {
    const req: Record<string, string[]> = { c: ["b"], b: ["a"], a: [] };
    expect([...ancestors("c", (id) => req[id] ?? [])].sort()).toEqual(["a", "b"]);
  });
});
