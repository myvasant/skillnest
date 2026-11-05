import { describe, expect, it } from "vitest";
import { compileContent, resolvePath } from "../../src/content/build";
import { loadContent } from "../../src/content/load";
import { concept, lesson, raw, smallCurriculum, stage } from "../helpers/fixtures";
import { projectRoot } from "../helpers/pyodide";

const errors = (c: ReturnType<typeof compileContent>) => c.issues.filter((i) => i.severity === "error").map((i) => i.message);

describe("real curriculum content", () => {
  const content = loadContent(projectRoot);
  it("has no validation errors", () => {
    expect(content.issues.filter((i) => i.severity === "error")).toEqual([]);
  });
  it("every lesson concept, path target and glossary link resolves", () => {
    for (const l of Object.values(content.index.lessons)) expect(content.index.concepts[l.concept]).toBeDefined();
    for (const p of content.index.paths) for (const t of p.targets) expect(content.index.concepts[t]).toBeDefined();
  });
  it("has a default path and at least one lesson with a mastery check", () => {
    expect(content.index.paths.some((p) => p.id === content.index.defaultPath)).toBe(true);
    expect(Object.values(content.index.lessons).some((l) => l.masteryItemIds.length >= 3)).toBe(true);
  });
  it("orders every concept after all of its prerequisites", () => {
    const pos = new Map(content.index.conceptOrder.map((id, i) => [id, i]));
    for (const c of Object.values(content.index.concepts)) for (const r of c.requires) expect(pos.get(r)!).toBeLessThan(pos.get(c.id)!);
  });
  it("search documents have unique ids and internal urls", () => {
    const ids = content.search.map((d) => d.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const d of content.search) expect(d.url.startsWith("/")).toBe(true);
  });
});

describe("compileContent validation", () => {
  it("accepts a small valid curriculum and derives reverse edges", () => {
    const c = smallCurriculum();
    expect(errors(c)).toEqual([]);
    expect(c.index.concepts.a!.requiredBy.sort()).toEqual(["b", "d"]);
    expect(c.index.concepts.b!.lessonId).toBe("lb");
    expect(c.index.items["la/q1"]).toMatchObject({ lessonId: "la", skill: "recognition", mastery: true, concepts: ["a"] });
    expect(c.index.concepts.a!.depth).toBe(0);
    expect(c.index.concepts.c!.depth).toBe(2);
  });

  it("resolves a path to its prerequisite closure in order", () => {
    const c = smallCurriculum();
    expect(c.index.paths[0]!.conceptIds).toEqual(["a", "b", "c", "d"]);
    expect(resolvePath(["c"], c.index.concepts, c.index.conceptOrder)).toEqual(["a", "b", "c"]);
  });

  it("reports duplicate concept ids", () => {
    const c = compileContent(raw({ stageData: [stage([concept("a"), concept("a")])] }));
    expect(errors(c).join()).toMatch(/duplicate concept id "a"/);
  });

  it("reports unknown prerequisites and self references", () => {
    const c = compileContent(raw({ stageData: [stage([concept("a", ["ghost"]), concept("b", ["b"])])] }));
    expect(errors(c).join()).toMatch(/unknown concept "ghost"/);
    expect(errors(c).join()).toMatch(/cannot reference itself/);
  });

  it("detects prerequisite cycles", () => {
    const c = compileContent(raw({ stageData: [stage([concept("a", ["c"]), concept("b", ["a"]), concept("c", ["b"])])] }));
    expect(errors(c).join()).toMatch(/prerequisite cycle/);
  });

  it("rejects unknown keys (strict schema) and invalid ids", () => {
    const typo = { ...concept("Bad Id"), sumary: "typo" } as ReturnType<typeof concept>;
    const c = compileContent(raw({ stageData: [stage([typo])] }));
    const msgs = c.issues.map((i) => `${i.path}: ${i.message}`).join("\n");
    expect(msgs).toMatch(/lowercase/);
    expect(msgs).toMatch(/sumary|Unrecognized key/i);
  });

  it("reports lessons for unknown concepts and two lessons for one concept", () => {
    const c = compileContent(raw({ stageData: [stage([concept("a")])], lessonData: [lesson("l1", "nope"), lesson("l2", "a"), lesson("l3", "a")] }));
    expect(errors(c).join()).toMatch(/unknown concept "nope"/);
    expect(errors(c).join()).toMatch(/already has lesson "l2"/);
  });

  it("reports broken item references and mastery items", () => {
    const l = lesson("l1", "a", { masteryCheck: { items: ["q1", "q2", "missing"] } });
    (l.sections[0]!.blocks as unknown[]).push({ type: "item", ref: "nowhere" });
    const c = compileContent(raw({ stageData: [stage([concept("a")])], lessonData: [l] }));
    expect(errors(c).join()).toMatch(/unknown item "nowhere"/);
    expect(errors(c).join()).toMatch(/unknown item "missing"/);
  });

  it("requires a correct option in multiple-choice questions", () => {
    const l = lesson("l1", "a");
    (l.items as unknown[]).push({
      id: "bad",
      type: "mcq",
      skill: "recognition",
      prompt: "Pick one.",
      explanation: "None are right.",
      options: [
        { id: "a", text: "x", feedback: "nope" },
        { id: "b", text: "y", feedback: "nope" },
      ],
    });
    const c = compileContent(raw({ stageData: [stage([concept("a")])], lessonData: [l] }));
    expect(errors(c).join()).toMatch(/no correct option/);
  });

  it("validates visualization ids and props", () => {
    const l = lesson("l1", "a");
    (l.sections[0]!.blocks as unknown[]).push(
      { type: "visualization", component: "warp-drive" },
      { type: "visualization", component: "python-tracer", props: { code: "" } },
    );
    const c = compileContent(raw({ stageData: [stage([concept("a")])], lessonData: [l] }));
    expect(errors(c).join()).toMatch(/unknown visualization "warp-drive"/);
    expect(c.issues.some((i) => i.path.includes("props.code"))).toBe(true);
  });

  it("reports broken internal markdown links", () => {
    const l = lesson("l1", "a");
    (l.sections[0]!.blocks as unknown[]).push({ type: "markdown", body: "See [x](concept:nope) and [y](glossary:missing) and [z](concept:a)." });
    const c = compileContent(raw({ stageData: [stage([concept("a")])], lessonData: [l] }));
    expect(errors(c)).toEqual(expect.arrayContaining([expect.stringMatching(/concept:nope/), expect.stringMatching(/glossary:missing/)]));
    expect(errors(c).join()).not.toMatch(/concept:a\b/);
  });

  it("reports unknown path targets and default path", () => {
    const c = compileContent(
      raw({
        stageData: [stage([concept("a")])],
        paths: {
          file: "paths.yaml",
          data: { defaultPath: "zzz", paths: [{ id: "p", title: "P", role: "r", summary: "s", outcomes: ["o"], targets: ["nope"] }] },
        },
      }),
    );
    expect(errors(c).join()).toMatch(/unknown default path/);
    expect(errors(c).join()).toMatch(/targets unknown concept "nope"/);
  });

  it("makes contrast/confusion relations symmetric", () => {
    const c = compileContent(raw({ stageData: [stage([concept("a", [], { confusedWith: ["b"] }), concept("b")])] }));
    expect(c.index.concepts.b!.confusedWith).toEqual(["a"]);
  });
});
