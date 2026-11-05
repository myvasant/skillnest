// Props accepted by each interactive visualization a lesson can embed.
// Validated at build time so a typo in lesson YAML fails the content check
// instead of rendering a broken widget.
import { z } from "zod";

const StepDiagramNode = z.strictObject({
  id: z.string(),
  label: z.string(),
  x: z.number(),
  y: z.number(),
  detail: z.string().optional(),
  shape: z.enum(["box", "pill", "store", "actor"]).default("box"),
});

const StepDiagramEdge = z.strictObject({
  id: z.string(),
  from: z.string(),
  to: z.string(),
  label: z.string().optional(),
});

const StepDiagramStep = z.strictObject({
  title: z.string(),
  body: z.string(),
  active: z.array(z.string()).default([]),
  payload: z.string().optional(),
});

export const visualizationSchemas = {
  /** Step through Python code: names, objects, call stack, output. Runs in Pyodide. */
  "python-tracer": z.strictObject({
    code: z.string().min(1),
    stdin: z.string().optional(),
    /** Show ints/strs as separate objects (accurate model) instead of inline values. */
    showPrimitivesAsObjects: z.boolean().default(true),
    maxSteps: z.number().int().positive().max(2000).default(300),
  }),
  /** A data-driven diagram whose nodes/edges light up step by step. */
  "step-diagram": z.strictObject({
    width: z.number().positive().default(720),
    height: z.number().positive().default(320),
    nodes: z.array(StepDiagramNode).min(2),
    edges: z.array(StepDiagramEdge).default([]),
    steps: z.array(StepDiagramStep).min(2),
  }),
  /** Interactive 2-D vectors: dot product, cosine similarity, Euclidean distance. */
  "vector-similarity": z.strictObject({
    a: z.tuple([z.number(), z.number()]).default([3, 1]),
    b: z.tuple([z.number(), z.number()]).default([1, 2]),
  }),
  /** Compare growth of O(1), O(log n), O(n), O(n log n), O(n^2), O(2^n). */
  "complexity-growth": z.strictObject({
    maxN: z.number().int().positive().max(64).default(32),
  }),
  /** BFS/DFS on a small graph with a visible frontier. */
  "graph-traversal": z.strictObject({
    nodes: z.array(z.strictObject({ id: z.string(), x: z.number(), y: z.number() })).min(2),
    edges: z.array(z.tuple([z.string(), z.string()])).min(1),
    start: z.string(),
    directed: z.boolean().default(false),
  }),
  /** Gradient descent on f(x) = (x - target)^2 with an adjustable learning rate. */
  "gradient-descent": z.strictObject({
    target: z.number().default(3),
    start: z.number().default(-4),
    learningRate: z.number().positive().default(0.1),
  }),
  /** INNER / LEFT / RIGHT / FULL joins on two small tables. */
  "sql-join": z.strictObject({
    left: z.strictObject({
      name: z.string(),
      key: z.string(),
      columns: z.array(z.string()),
      rows: z.array(z.array(z.union([z.string(), z.number(), z.null()]))),
    }),
    right: z.strictObject({
      name: z.string(),
      key: z.string(),
      columns: z.array(z.string()),
      rows: z.array(z.array(z.union([z.string(), z.number(), z.null()]))),
    }),
  }),
  /** A tiny neural network: adjust inputs and weights, watch activations propagate. */
  "neural-forward": z.strictObject({
    inputs: z.array(z.number()).min(1).max(4).default([1, 0.5]),
  }),
  /** Scaled dot-product attention over a handful of tokens. */
  attention: z.strictObject({
    tokens: z.array(z.string()).min(2).max(6).default(["the", "cat", "sat"]),
  }),
} as const;

export type VisualizationId = keyof typeof visualizationSchemas;
export const visualizationIds = Object.keys(visualizationSchemas) as VisualizationId[];

export function isVisualizationId(id: string): id is VisualizationId {
  return id in visualizationSchemas;
}
