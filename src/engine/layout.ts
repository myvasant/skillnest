// Layered layout for small DAGs (one curriculum stage at a time).
// Layer = longest path from a root within the subgraph; order within a layer
// is improved with a few barycenter sweeps to reduce edge crossings.

export interface LayoutInput {
  ids: string[];
  /** Edges as [prerequisite, dependent]. Edges to ids outside `ids` are ignored. */
  edges: [string, string][];
}

export interface LayoutNode {
  id: string;
  layer: number;
  order: number;
  x: number;
  y: number;
}

export interface LayoutResult {
  nodes: Record<string, LayoutNode>;
  edges: [string, string][];
  width: number;
  height: number;
  layers: string[][];
}

export function layeredLayout(input: LayoutInput, opts = { nodeWidth: 210, nodeHeight: 52, colGap: 70, rowGap: 18, pad: 16 }): LayoutResult {
  const idSet = new Set(input.ids);
  const edges = input.edges.filter(([a, b]) => idSet.has(a) && idSet.has(b) && a !== b);
  const parents = new Map<string, string[]>(input.ids.map((id) => [id, []]));
  const children = new Map<string, string[]>(input.ids.map((id) => [id, []]));
  for (const [a, b] of edges) {
    parents.get(b)!.push(a);
    children.get(a)!.push(b);
  }

  const layer = new Map<string, number>();
  const visiting = new Set<string>();
  const depth = (id: string): number => {
    if (layer.has(id)) return layer.get(id)!;
    if (visiting.has(id)) return 0; // cycle guard (content validation rejects cycles)
    visiting.add(id);
    const d = parents.get(id)!.reduce((m, p) => Math.max(m, depth(p) + 1), 0);
    visiting.delete(id);
    layer.set(id, d);
    return d;
  };
  input.ids.forEach(depth);

  const layerCount = Math.max(0, ...layer.values()) + 1;
  const layers: string[][] = Array.from({ length: layerCount }, () => []);
  for (const id of input.ids) layers[layer.get(id)!]!.push(id);

  const position = new Map<string, number>();
  const reindex = () => layers.forEach((l) => l.forEach((id, i) => position.set(id, i)));
  reindex();
  const bary = (id: string, neighbours: string[]) =>
    neighbours.length ? neighbours.reduce((s, n) => s + position.get(n)!, 0) / neighbours.length : position.get(id)!;
  for (let sweep = 0; sweep < 4; sweep++) {
    for (let i = 1; i < layers.length; i++) {
      layers[i]!.sort((a, b) => bary(a, parents.get(a)!) - bary(b, parents.get(b)!));
      reindex();
    }
    for (let i = layers.length - 2; i >= 0; i--) {
      layers[i]!.sort((a, b) => bary(a, children.get(a)!) - bary(b, children.get(b)!));
      reindex();
    }
  }

  const tallest = Math.max(1, ...layers.map((l) => l.length));
  const height = opts.pad * 2 + tallest * opts.nodeHeight + (tallest - 1) * opts.rowGap;
  const nodes: Record<string, LayoutNode> = {};
  layers.forEach((ids, li) => {
    // Top-aligned columns read better than centred ones when layers differ a lot in size.
    const offset = opts.pad;
    ids.forEach((id, oi) => {
      nodes[id] = {
        id,
        layer: li,
        order: oi,
        x: opts.pad + li * (opts.nodeWidth + opts.colGap),
        y: offset + oi * (opts.nodeHeight + opts.rowGap),
      };
    });
  });
  const width = opts.pad * 2 + layerCount * opts.nodeWidth + Math.max(0, layerCount - 1) * opts.colGap;
  return { nodes, edges, width, height, layers };
}

/** All ancestors (transitive prerequisites) of a node within a relation map. */
export function ancestors(id: string, requires: (id: string) => string[]): Set<string> {
  const out = new Set<string>();
  const stack = [...requires(id)];
  while (stack.length) {
    const n = stack.pop()!;
    if (out.has(n)) continue;
    out.add(n);
    stack.push(...requires(n));
  }
  return out;
}
