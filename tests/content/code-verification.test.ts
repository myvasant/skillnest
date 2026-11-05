// Executes every Python example, prediction question, exercise solution and
// tracer program in the curriculum with the same Pyodide runtime learners use.
// This is what backs the "verified" badge shown on lesson code.
import { beforeAll, describe, expect, it } from "vitest";
import type { PyodideAPI } from "pyodide";
import { loadContent } from "../../src/content/load";
import { gradeCode, runCode } from "../../src/python/host";
import { normalizeOutput } from "../../src/engine/output";
import { getPyodide, projectRoot } from "../helpers/pyodide";

const content = loadContent(projectRoot);
let py: PyodideAPI;

beforeAll(async () => {
  py = await getPyodide();
});

const describeError = (r: ReturnType<typeof runCode>) => (r.error ? `${r.error.type}: ${r.error.message}\n${r.error.traceback}` : "");

for (const lesson of Object.values(content.lessons)) {
  describe(`lesson ${lesson.id}`, () => {
    lesson.sections.forEach((section) => {
      section.blocks.forEach((block, bi) => {
        if (block.type === "code" && block.language === "python" && block.status !== "illustrative" && block.status !== "pseudocode") {
          it(`code block ${section.id}#${bi} runs as documented`, () => {
            const result = runCode(py, block.code, block.stdin ?? "");
            if (block.expectError) {
              expect(result.error?.type, "expected this example to raise").toBe(block.expectError);
            } else {
              expect(result.error, describeError(result)).toBeNull();
            }
            if (block.expectedOutput !== undefined) {
              expect(normalizeOutput(result.stdout)).toBe(normalizeOutput(block.expectedOutput));
            }
          });
        }
        if (block.type === "visualization" && block.component === "python-tracer") {
          it(`tracer program ${section.id}#${bi} runs without errors`, () => {
            const props = block.props as { code: string; stdin?: string };
            const result = runCode(py, props.code, props.stdin ?? "");
            expect(result.error, describeError(result)).toBeNull();
          });
        }
      });
    });

    for (const item of lesson.items) {
      if (item.type === "predict-output") {
        it(`prediction ${item.id}: answer matches real output`, () => {
          const result = runCode(py, item.code);
          expect(normalizeOutput(result.stdout)).toBe(normalizeOutput(item.answer));
          for (const wrong of item.wrongAnswers) {
            expect(normalizeOutput(wrong.answer), "a 'wrong answer' must not equal the right one").not.toBe(normalizeOutput(item.answer));
          }
        });
      }
      if (item.type === "code" || item.type === "debug") {
        it(`exercise ${item.id}: reference solution passes every test`, () => {
          const graded = gradeCode(py, item.solution, item.tests, item.stdin ?? "");
          const failures = graded.tests.filter((t) => !t.passed).map((t) => `${t.name}: ${t.message}`);
          expect(graded.run.error, describeError(graded.run)).toBeNull();
          expect(failures).toEqual([]);
          if (item.expectedOutput !== undefined) {
            expect(normalizeOutput(graded.run.stdout)).toBe(normalizeOutput(item.expectedOutput));
          }
        });
        it(`exercise ${item.id}: starter code does not already pass`, () => {
          const graded = gradeCode(py, item.starterCode, item.tests, item.stdin ?? "");
          expect(graded.passed).toBe(false);
        });
        for (const rule of item.feedback) {
          if (rule.when.codeMatches) {
            it(`exercise ${item.id}: feedback regex compiles`, () => {
              expect(() => new RegExp(rule.when.codeMatches!)).not.toThrow();
            });
          }
        }
      }
      if (item.type === "parsons" && item.expectedOutput !== undefined) {
        it(`parsons ${item.id}: solution produces the expected output`, () => {
          const result = runCode(py, item.solution);
          expect(result.error, describeError(result)).toBeNull();
          expect(normalizeOutput(result.stdout)).toBe(normalizeOutput(item.expectedOutput!));
        });
      }
    }
  });
}

for (const project of Object.values(content.projects)) {
  for (const milestone of project.milestones) {
    if (milestone.tests.length && milestone.solution) {
      it(`project ${project.id} milestone ${milestone.id}: reference solution passes`, async () => {
        const graded = gradeCode(py, milestone.solution!, milestone.tests);
        expect(graded.tests.filter((t) => !t.passed).map((t) => `${t.name}: ${t.message}`)).toEqual([]);
      });
    }
  }
}
