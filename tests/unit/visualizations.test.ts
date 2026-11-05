// The visualizations compute what they display; these tests check that the
// numbers they show match the underlying definitions.
import { describe, expect, it } from "vitest";
import { similarity } from "../../src/features/visualizations/VectorSimilarity";
import { traverse } from "../../src/features/visualizations/GraphTraversal";
import { descend } from "../../src/features/visualizations/GradientDescent";
import { joinTables } from "../../src/features/visualizations/SqlJoin";
import { forward } from "../../src/features/visualizations/NeuralForward";
import { attention } from "../../src/features/visualizations/Attention";
import { classes } from "../../src/features/visualizations/ComplexityGrowth";

describe("vector similarity", () => {
  it("computes dot product, cosine, angle and distance", () => {
    const s = similarity([3, 4], [4, 3]);
    expect(s.dot).toBe(24);
    expect(s.na).toBe(5);
    expect(s.cosine).toBeCloseTo(0.96);
    expect(s.distance).toBeCloseTo(Math.SQRT2);
  });
  it("cosine is 1 for parallel vectors of different length and -1 for opposite", () => {
    expect(similarity([1, 1], [4, 4]).cosine).toBeCloseTo(1);
    expect(similarity([2, 1], [-2, -1]).cosine).toBeCloseTo(-1);
    expect(similarity([3, 0], [0, 2]).angle).toBeCloseTo(90);
  });
  it("is undefined for the zero vector", () => {
    expect(similarity([0, 0], [1, 2]).cosine).toBeNaN();
  });
});

describe("graph traversal", () => {
  const nodes = ["A", "B", "C", "D", "E"];
  const edges: [string, string][] = [
    ["A", "B"],
    ["A", "C"],
    ["B", "D"],
    ["C", "D"],
    ["D", "E"],
  ];
  it("BFS visits level by level", () => {
    const steps = traverse("bfs", nodes, edges, "A", false);
    expect(steps.at(-1)!.visited).toEqual(["A", "B", "C", "D", "E"]);
  });
  it("DFS goes deep first, alphabetical neighbour order", () => {
    const steps = traverse("dfs", nodes, edges, "A", false);
    expect(steps.at(-1)!.visited).toEqual(["A", "B", "D", "C", "E"]);
  });
  it("respects edge direction", () => {
    const steps = traverse("bfs", nodes, edges, "D", true);
    expect(steps.at(-1)!.visited).toEqual(["D", "E"]);
  });
});

describe("gradient descent", () => {
  it("converges for small learning rates and follows x ← x − η·2(x − t)", () => {
    const path = descend(-4, 3, 0.1, 50);
    expect(path[1]!.x).toBeCloseTo(-4 - 0.1 * 2 * (-4 - 3));
    expect(Math.abs(path.at(-1)!.x - 3)).toBeLessThan(1e-3);
  });
  it("oscillates forever at η = 1 and diverges above it", () => {
    const osc = descend(-4, 3, 1, 4);
    expect(osc.map((p) => p.x)).toEqual([-4, 10, -4, 10, -4]);
    const div = descend(-4, 3, 1.1, 10);
    expect(Math.abs(div.at(-1)!.x - 3)).toBeGreaterThan(Math.abs(div[0]!.x - 3));
  });
});

describe("sql joins", () => {
  const left = { name: "users", key: "id", columns: ["id", "name"], rows: [[1, "Ada"], [2, "Linus"], [3, "Grace"], [null, "Ghost"]] };
  const right = { name: "orders", key: "user_id", columns: ["order", "user_id"], rows: [[10, 1], [11, 1], [12, 3], [13, 9]] };
  const ids = (kind: "INNER" | "LEFT" | "RIGHT" | "FULL") => joinTables(left, right, kind).map((r) => [r.l?.[1] ?? null, r.r?.[0] ?? null]);
  it("INNER keeps only matches (one row per matching pair)", () => {
    expect(ids("INNER")).toEqual([["Ada", 10], ["Ada", 11], ["Grace", 12]]);
  });
  it("LEFT keeps unmatched left rows, and NULL keys never match", () => {
    expect(ids("LEFT")).toEqual([["Ada", 10], ["Ada", 11], ["Linus", null], ["Grace", 12], ["Ghost", null]]);
  });
  it("RIGHT and FULL keep unmatched right rows", () => {
    expect(ids("RIGHT")).toContainEqual([null, 13]);
    expect(ids("FULL")).toHaveLength(6);
  });
});

describe("neural network forward pass", () => {
  it("computes z = W·x + b and the activations", () => {
    const r = forward([1, 0.5], [[1, -1], [0.5, 0.5]], [0, -0.5], [1.5, -1], 0, "relu");
    expect(r.z1).toEqual([0.5, 0.25]);
    expect(r.a1).toEqual([0.5, 0.25]);
    expect(r.z2).toBeCloseTo(0.5);
    expect(r.out).toBeCloseTo(1 / (1 + Math.exp(-0.5)));
  });
  it("ReLU zeroes negative pre-activations", () => {
    expect(forward([-1], [[1], [2]], [0, 0], [1, 1], 0, "relu").a1).toEqual([0, 0]);
  });
});

describe("attention", () => {
  it("each row of weights is a probability distribution", () => {
    const r = attention(["the", "cat", "sat", "down"], false, 1);
    for (const row of r.weights) {
      expect(row.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
      for (const w of row) expect(w).toBeGreaterThanOrEqual(0);
    }
    expect(r.out[0]![0]).toBeCloseTo(r.weights[0]!.reduce((s, w, j) => s + w * r.V[j]![0]!, 0));
  });
  it("the causal mask gives zero weight to future tokens", () => {
    const r = attention(["a", "b", "c"], true, 1);
    expect(r.weights[0]).toEqual([1, 0, 0]);
    expect(r.weights[1]![2]).toBe(0);
  });
});

describe("visual explorer presets", () => {
  it("every preset has valid props and unique ids", async () => {
    const { presets } = await import("../../src/features/visualizations/presets");
    const { visualizationSchemas } = await import("../../src/content/visualizationSchemas");
    const ids = presets.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const p of presets) {
      const parsed = visualizationSchemas[p.component].safeParse(p.props);
      expect(parsed.success, `${p.id}: ${parsed.success ? "" : JSON.stringify(parsed.error.issues)}`).toBe(true);
    }
  });
  it("step diagrams only activate nodes and edges that exist", async () => {
    const { presets } = await import("../../src/features/visualizations/presets");
    for (const p of presets.filter((x) => x.component === "step-diagram")) {
      const props = p.props as { nodes: { id: string }[]; edges: { id: string; from: string; to: string }[]; steps: { active: string[] }[] };
      const known = new Set([...props.nodes.map((n) => n.id), ...props.edges.map((e) => e.id)]);
      for (const e of props.edges) expect(known.has(e.from) && known.has(e.to), `${p.id}: edge ${e.id}`).toBe(true);
      for (const s of props.steps) for (const a of s.active) expect(known.has(a), `${p.id}: unknown active id ${a}`).toBe(true);
    }
  });
});

describe("complexity classes", () => {
  it("orders growth as expected at n = 32", () => {
    const v = classes.map((c) => c.f(32));
    expect(v).toEqual([...v].sort((a, b) => a - b));
    expect(classes.find((c) => c.id === "n2")!.f(32)).toBe(1024);
  });
});
