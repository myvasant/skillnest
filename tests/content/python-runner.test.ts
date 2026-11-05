// Integration tests for python/gw_runner.py running inside Pyodide.
import { beforeAll, describe, expect, it } from "vitest";
import type { PyodideAPI } from "pyodide";
import { gradeCode, runCode, traceCode } from "../../src/python/host";
import { getPyodide } from "../helpers/pyodide";

let py: PyodideAPI;
beforeAll(async () => {
  py = await getPyodide();
});

describe("run", () => {
  it("captures stdout, stderr and timing", () => {
    const r = runCode(py, "import sys\nprint('out')\nprint('err', file=sys.stderr)");
    expect(r).toMatchObject({ status: "completed", ok: true, stdout: "out\n", stderr: "err\n", error: null });
    expect(r.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("feeds input() from stdin and records where values were read", () => {
    const r = runCode(py, "a = input('A? ')\nb = input('B? ')\nprint(a + b)", "x\ny\n");
    expect(r.stdout).toBe("A? B? xy\n");
    expect(r.events).toEqual([
      { kind: "input", at: 3, value: "x" },
      { kind: "input", at: 6, value: "y" },
    ]);
  });

  it("raises a helpful EOFError when input runs out", () => {
    const r = runCode(py, "input()");
    expect(r.error).toMatchObject({ type: "EOFError", line: 1 });
    expect(r.error!.message).toMatch(/Input box/);
  });

  it("reports runtime errors with learner line numbers and hides runner frames", () => {
    const r = runCode(py, "x = 1\ndef f():\n    return y\nf()");
    expect(r.error).toMatchObject({ type: "NameError", line: 3 });
    expect(r.error!.traceback).toContain('File "<learner>", line 4');
    expect(r.error!.traceback).not.toContain("gw_runner");
    expect(r.error!.traceback).toMatch(/Did you mean|not defined/);
  });

  it("reports syntax errors with position, and runs nothing", () => {
    const r = runCode(py, "print('a')\nif True\n    print('b')");
    expect(r.stdout).toBe("");
    expect(r.error).toMatchObject({ type: "SyntaxError", line: 2 });
  });

  it("stops runaway output", () => {
    const r = runCode(py, "while True:\n    print('spam' * 100)");
    expect(r.error?.type).toBe("OutputLimitExceeded");
    expect(r.stdout.length).toBeLessThanOrEqual(200_000);
  });

  it("treats sys.exit(0) as success and other codes as errors", () => {
    expect(runCode(py, "import sys\nprint(1)\nsys.exit(0)\nprint(2)")).toMatchObject({ ok: true, stdout: "1\n", exitCode: 0 });
    expect(runCode(py, "import sys\nsys.exit(3)")).toMatchObject({ ok: false, exitCode: 3 });
  });

  it("does not leak the runner's __future__ imports into learner code", () => {
    const r = runCode(py, "def f(x: int) -> int:\n    return x\nprint(f.__annotations__)");
    expect(r.stdout.trim()).toBe("{'x': <class 'int'>, 'return': <class 'int'>}");
  });

  it("isolates runs: names from one run are not visible in the next", () => {
    runCode(py, "secret = 42");
    expect(runCode(py, "print(secret)").error?.type).toBe("NameError");
  });

  it("patches input() only while a run is in progress", () => {
    expect(runCode(py, "import builtins\nprint(builtins.input.__module__)").stdout.trim()).toBe("gw_runner");
    expect(py.runPython("import builtins, sys\n(builtins.input.__module__, sys.stdout.__class__.__name__)").toJs()).toEqual([
      "builtins",
      expect.not.stringContaining("_Capture"),
    ]);
  });
});

describe("trace", () => {
  it("records line, call and return events with frames and shared objects", () => {
    const t = traceCode(py, "a = [1]\nb = a\ndef f(n):\n    return n + 1\nc = f(2)\n");
    const events = t.steps.map((s) => `${s.event}:${s.line}`);
    expect(events).toEqual(["line:1", "line:2", "line:3", "line:5", "call:3", "line:4", "return:4", "return:5"]);
    const afterAlias = t.steps[2]!;
    const vars = Object.fromEntries(afterAlias.stack[0]!.vars.map((v) => [v.name, v.ref]));
    expect(vars.a).toBe(vars.b);
    expect(afterAlias.heap[String(vars.a)]).toMatchObject({ kind: "list", type: "list" });
    const ret = t.steps.find((s) => s.event === "return" && s.stack.length === 2)!;
    expect(ret.heap[String(ret.returnRef)]).toMatchObject({ kind: "primitive", repr: "3" });
  });

  it("reports a generator's yield as 'yield' (paused), not 'return' (finished)", () => {
    const t = traceCode(py, "def gen():\n    yield 1\n    yield 2\n\ng = gen()\nprint(next(g))\nprint(next(g))\n");
    const genSteps = t.steps.filter((s) => s.stack.at(-1)?.name === "gen");
    expect(genSteps.filter((s) => s.event === "yield").map((s) => s.heap[String(s.returnRef)]?.repr)).toEqual(["1", "2"]);
    expect(genSteps.some((s) => s.event === "return")).toBe(false);
    expect(t.stdout).toBe("1\n2\n");
  });

  it("keeps object labels stable across steps", () => {
    const t = traceCode(py, "x = 'hello'\ny = 1\nz = x\n");
    const ref = (i: number, name: string) => t.steps[i]!.stack[0]!.vars.find((v) => v.name === name)?.ref;
    expect(ref(2, "x")).toBe(ref(3, "x"));
    expect(ref(3, "z")).toBe(ref(3, "x"));
  });

  it("stops at the step limit and says so", () => {
    const t = traceCode(py, "i = 0\nwhile True:\n    i += 1", "", 50);
    expect(t.steps.length).toBe(50);
    expect(t.truncated).toBe(true);
  });
});

describe("sql-join visualization matches real SQL", () => {
  it("produces the same rows as SQLite for every join type", async () => {
    const { joinTables } = await import("../../src/features/visualizations/SqlJoin");
    const left = { name: "users", key: "id", columns: ["id", "name"], rows: [[1, "Ada"], [2, "Linus"], [3, "Grace"], [null, "Ghost"]] as (string | number | null)[][] };
    const right = { name: "orders", key: "user_id", columns: ["order_id", "user_id"], rows: [[10, 1], [11, 1], [12, 3], [13, 9]] as (string | number | null)[][] };
    const lit = (v: unknown) => (v === null ? "NULL" : typeof v === "string" ? `'${v}'` : String(v));
    const setup = [
      "import sqlite3, json",
      "con = sqlite3.connect(':memory:')",
      "con.execute('CREATE TABLE users (id INTEGER, name TEXT)')",
      "con.execute('CREATE TABLE orders (order_id INTEGER, user_id INTEGER)')",
      ...left.rows.map((r) => `con.execute("INSERT INTO users VALUES (${r.map(lit).join(", ")})")`),
      ...right.rows.map((r) => `con.execute("INSERT INTO orders VALUES (${r.map(lit).join(", ")})")`),
    ];
    for (const kind of ["INNER", "LEFT", "RIGHT", "FULL"] as const) {
      const sqlKind = kind === "FULL" ? "FULL OUTER" : kind;
      const code = [...setup, `rows = con.execute("SELECT users.id, users.name, orders.order_id, orders.user_id FROM users ${sqlKind} JOIN orders ON users.id = orders.user_id").fetchall()`, "print(json.dumps(sorted(rows, key=repr)))"].join("\n");
      const result = runCode(py, code);
      expect(result.error, result.error?.message).toBeNull();
      const fromSql = JSON.parse(result.stdout) as unknown[][];
      const fromViz = joinTables(left, right, kind).map((r) => [...(r.l ?? [null, null]), ...(r.r ?? [null, null])]);
      const key = (rows: unknown[][]) => rows.map((r) => JSON.stringify(r)).sort();
      expect(key(fromViz)).toEqual(key(fromSql));
    }
  });
});

describe("grade", () => {
  it("passes tests and exposes helper functions", () => {
    const g = gradeCode(py, "def add(a, b):\n    return a + b\nprint(add(2, 3))", [
      { name: "add works", code: "assert add(2, 3) == 5" },
      { name: "output", code: "assert output() == '5\\n' and output_lines() == ['5']" },
      { name: "structure", code: "assert uses('FunctionDef', 'Return') and calls('add') and defined('add')" },
    ]);
    expect(g.passed).toBe(true);
  });

  it("explains failed asserts with the message or the failing line", () => {
    const g = gradeCode(py, "x = 1", [
      { name: "with message", code: "assert x == 2, 'x should be 2'" },
      { name: "without message", code: "assert x == 3" },
      { name: "error", code: "missing_name" },
    ]);
    expect(g.passed).toBe(false);
    expect(g.tests.map((t) => t.message)).toEqual(["x should be 2", "This check failed: assert x == 3", "NameError: name 'missing_name' is not defined"]);
  });

  it("re-runs the program with other input via run_program", () => {
    const g = gradeCode(py, "n = int(input())\nprint(n * 2)", [{ name: "doubles", code: "assert run_program('21\\n') == '42\\n'" }], "1\n");
    expect(g.passed).toBe(true);
  });

  it("does not run tests when the program has a syntax error", () => {
    const g = gradeCode(py, "def (", [{ name: "t", code: "assert True" }]);
    expect(g.passed).toBe(false);
    expect(g.tests[0]!.message).toMatch(/syntax error/);
  });

  it("fails when the program raises, even if tests pass", () => {
    const g = gradeCode(py, "x = 1\n1/0", [{ name: "x", code: "assert x == 1" }]);
    expect(g.tests[0]!.passed).toBe(true);
    expect(g.passed).toBe(false);
  });

  it("captures what learner code prints during a test separately", () => {
    const g = gradeCode(py, "def hi():\n    print('hi')\n    return 1", [{ name: "t", code: "assert hi() == 1" }]);
    expect(g.tests[0]!.printed).toBe("hi\n");
    expect(g.run.stdout).toBe("");
  });
});
