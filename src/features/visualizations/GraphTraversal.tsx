// Breadth-first vs depth-first search with a visible frontier (queue or stack).
import { useMemo, useState } from "react";
import { cn } from "../../components/ui";
import { StepControls, useStepper } from "./controls";

interface Props {
  nodes: { id: string; x: number; y: number }[];
  edges: [string, string][];
  start: string;
  directed: boolean;
}

interface Snapshot {
  current: string | null;
  visited: string[];
  frontier: string[];
  note: string;
}

export function traverse(algo: "bfs" | "dfs", nodes: string[], edges: [string, string][], start: string, directed: boolean): Snapshot[] {
  const adj = new Map<string, string[]>(nodes.map((n) => [n, []]));
  for (const [a, b] of edges) {
    adj.get(a)?.push(b);
    if (!directed) adj.get(b)?.push(a);
  }
  for (const list of adj.values()) list.sort();
  const steps: Snapshot[] = [{ current: null, visited: [], frontier: [start], note: `Start: put ${start} in the ${algo === "bfs" ? "queue" : "stack"}.` }];
  const visited: string[] = [];
  const frontier = [start];
  while (frontier.length) {
    const node = algo === "bfs" ? frontier.shift()! : frontier.pop()!;
    if (visited.includes(node)) {
      steps.push({ current: node, visited: [...visited], frontier: [...frontier], note: `${node} was already visited — skip it.` });
      continue;
    }
    visited.push(node);
    const neighbours = adj.get(node) ?? [];
    // BFS enqueues a node once, when first discovered. DFS pushes every unvisited
    // neighbour (even if already on the stack) so the visit order matches the
    // recursive definition; stale stack entries are skipped when popped.
    const fresh = neighbours.filter((n) => !visited.includes(n) && (algo === "dfs" || !frontier.includes(n)));
    if (algo === "bfs") frontier.push(...fresh);
    else frontier.push(...[...fresh].reverse());
    steps.push({
      current: node,
      visited: [...visited],
      frontier: [...frontier],
      note: `Visit ${node}. ${fresh.length ? `Add unvisited neighbours ${fresh.join(", ")} to the ${algo === "bfs" ? "back of the queue" : "top of the stack"}.` : "No new neighbours."}`,
    });
  }
  steps.push({ current: null, visited: [...visited], frontier: [], note: `Done. Visit order: ${visited.join(" → ")}.` });
  return steps;
}

export function GraphTraversal({ nodes, edges, start, directed }: Props) {
  const [algo, setAlgo] = useState<"bfs" | "dfs">("bfs");
  const steps = useMemo(() => traverse(algo, nodes.map((n) => n.id).sort(), edges, start, directed), [algo, nodes, edges, start, directed]);
  const stepper = useStepper(steps.length, 1300);
  const s = steps[Math.min(stepper.index, steps.length - 1)]!;
  const pos = new Map(nodes.map((n) => [n.id, n]));
  const maxX = Math.max(...nodes.map((n) => n.x)) + 40;
  const maxY = Math.max(...nodes.map((n) => n.y)) + 40;

  return (
    <div className="grid gap-4 p-4 md:grid-cols-[minmax(0,1fr)_260px]">
      <div>
        <div role="radiogroup" aria-label="Algorithm" className="mb-3 inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
          {(["bfs", "dfs"] as const).map((a) => (
            <button
              key={a}
              role="radio"
              aria-checked={algo === a}
              onClick={() => {
                setAlgo(a);
                stepper.reset();
              }}
              className={cn("rounded-md px-3 py-1 text-[13px] font-medium", algo === a ? "bg-surface shadow-card" : "text-muted")}
            >
              {a === "bfs" ? "Breadth-first (queue)" : "Depth-first (stack)"}
            </button>
          ))}
        </div>
        <svg viewBox={`-30 -30 ${maxX + 30} ${maxY + 30}`} className="w-full" role="img" aria-label={`Graph. Visited: ${s.visited.join(", ") || "none"}.`}>
          {edges.map(([a, b]) => {
            const p = pos.get(a)!;
            const q = pos.get(b)!;
            const on = s.visited.includes(a) && s.visited.includes(b);
            return <line key={`${a}-${b}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={on ? "var(--gw-accent)" : "var(--gw-border-strong)"} strokeWidth={on ? 2 : 1.3} />;
          })}
          {nodes.map((n) => {
            const isCurrent = s.current === n.id;
            const isVisited = s.visited.includes(n.id);
            const inFrontier = s.frontier.includes(n.id);
            return (
              <g key={n.id}>
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={18}
                  fill={isCurrent ? "var(--gw-accent)" : isVisited ? "var(--gw-accent-soft)" : "var(--gw-surface)"}
                  stroke={inFrontier ? "var(--gw-warning)" : isVisited ? "var(--gw-accent)" : "var(--gw-border-strong)"}
                  strokeWidth={inFrontier || isCurrent ? 3 : 1.5}
                  strokeDasharray={inFrontier ? "4 2" : undefined}
                />
                <text x={n.x} y={n.y + 5} textAnchor="middle" className="text-[14px] font-semibold" fill={isCurrent ? "var(--gw-accent-fg)" : "var(--gw-text)"}>
                  {n.id}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="mt-2">
          <StepControls stepper={stepper} total={steps.length} />
        </div>
      </div>
      <div className="space-y-3 text-[13.5px]" aria-live="polite">
        <p className="rounded-lg bg-surface-2 px-3 py-2">{s.note}</p>
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wide text-muted">{algo === "bfs" ? "Queue (front → back)" : "Stack (bottom → top)"}</p>
          <p className="mt-1 min-h-7 font-mono">{s.frontier.length ? s.frontier.join("  ") : "empty"}</p>
        </div>
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wide text-muted">Visited, in order</p>
          <p className="mt-1 font-mono">{s.visited.join(" → ") || "—"}</p>
        </div>
        <p className="text-[12.5px] text-muted">
          Legend: filled = current, tinted = visited, dashed orange ring = waiting in the {algo === "bfs" ? "queue" : "stack"}. Neighbours are taken in alphabetical
          order so runs are reproducible.
        </p>
      </div>
    </div>
  );
}
