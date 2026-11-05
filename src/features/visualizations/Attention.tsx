// Scaled dot-product attention on toy 2-D vectors:
//   scores = Q·Kᵀ / √d,  weights = softmax(scores) per row,  output = weights · V
// Embeddings are deterministic toy vectors derived from each token (not learned),
// which is stated in the UI: the point is the mechanism, not real semantics.
import { useMemo, useState } from "react";
import { cn } from "../../components/ui";
import { fmt } from "./controls";

type M = number[][];

function toyEmbedding(token: string): [number, number] {
  let h = 2166136261;
  for (let i = 0; i < token.length; i++) h = Math.imul(h ^ token.charCodeAt(i), 16777619);
  const a = ((h >>> 0) % 1000) / 1000;
  const b = (((h >>> 0) / 1000) % 1000) / 1000;
  return [Number((a * 2 - 1).toFixed(2)), Number((b * 2 - 1).toFixed(2))];
}

const mul = (x: number[], W: M) => W[0]!.map((_, j) => x.reduce((s, xi, i) => s + xi * W[i]![j]!, 0));
const softmax = (row: number[]) => {
  const finite = row.filter(Number.isFinite);
  const m = Math.max(...finite);
  const e = row.map((v) => (Number.isFinite(v) ? Math.exp(v - m) : 0));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((v) => v / s);
};

const WQ: M = [
  [1.2, 0.3],
  [-0.4, 1.0],
];
const WK: M = [
  [0.9, -0.2],
  [0.5, 1.1],
];
const WV: M = [
  [1.0, 0.0],
  [0.0, 1.0],
];

export function attention(tokens: string[], causal: boolean, scale: number) {
  const X = tokens.map(toyEmbedding);
  const Q = X.map((x) => mul(x, WQ));
  const K = X.map((x) => mul(x, WK));
  const V = X.map((x) => mul(x, WV));
  const d = 2;
  const scores = Q.map((q, i) => K.map((k, j) => (causal && j > i ? -Infinity : ((q[0]! * k[0]! + q[1]! * k[1]!) / Math.sqrt(d)) * scale)));
  const weights = scores.map(softmax);
  const out = weights.map((w) => [0, 1].map((c) => w.reduce((s, wj, j) => s + wj * V[j]![c]!, 0)));
  return { X, Q, K, V, scores, weights, out };
}

export function Attention({ tokens }: { tokens: string[] }) {
  const [query, setQuery] = useState(tokens.length - 1);
  const [causal, setCausal] = useState(false);
  const [scale, setScale] = useState(1);
  const r = useMemo(() => attention(tokens, causal, scale), [tokens, causal, scale]);
  const vec = (v: number[]) => `[${v.map((x) => fmt(x, 2)).join(", ")}]`;

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-4 text-[13.5px]">
        <span>Query token:</span>
        <div role="radiogroup" aria-label="Query token" className="inline-flex flex-wrap gap-1">
          {tokens.map((t, i) => (
            <button key={i} role="radio" aria-checked={query === i} onClick={() => setQuery(i)} className={cn("rounded-md border px-2.5 py-1 font-mono text-[13px]", query === i ? "border-accent bg-accent-soft" : "border-border")}>
              {t}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={causal} onChange={(e) => setCausal(e.target.checked)} className="accent-[var(--gw-accent)]" />
          causal mask (GPT-style: no looking ahead)
        </label>
        <label className="flex items-center gap-2">
          score sharpness
          <input type="range" min={0.2} max={5} step={0.1} value={scale} onChange={(e) => setScale(Number(e.target.value))} className="accent-[var(--gw-accent)]" aria-label="Score sharpness" />
          <span className="w-8 font-mono">{scale.toFixed(1)}×</span>
        </label>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="overflow-x-auto">
          <p className="mb-1 text-[12.5px] font-semibold">Attention weights (each row sums to 1)</p>
          <table className="border-collapse text-[12.5px]">
            <thead>
              <tr>
                <th className="px-2 py-1 text-left text-[11px] font-normal text-muted">query ↓ / key →</th>
                {tokens.map((t, j) => (
                  <th key={j} className="px-2 py-1 font-mono font-medium">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.weights.map((row, i) => (
                <tr key={i} className={cn(i === query && "outline outline-2 outline-accent")}>
                  <th className="px-2 py-1 text-left font-mono font-medium">{tokens[i]}</th>
                  {row.map((w, j) => (
                    <td
                      key={j}
                      className="h-9 w-14 border border-border text-center font-mono"
                      style={{ background: `color-mix(in srgb, var(--gw-accent) ${Math.round(w * 85)}%, transparent)`, color: w > 0.55 ? "var(--gw-accent-fg)" : undefined }}
                      title={`${tokens[i]} → ${tokens[j]}: ${fmt(w, 3)}`}
                    >
                      {causal && j > i ? "—" : fmt(w, 2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="space-y-2 text-[13px]">
          <p className="font-semibold">
            How &ldquo;<span className="font-mono">{tokens[query]}</span>&rdquo; builds its output
          </p>
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>
              Query <span className="font-mono">q = x·W_Q = {vec(r.Q[query]!)}</span>
            </li>
            <li>
              Score against each key: <span className="font-mono">q·k / √2</span> →{" "}
              <span className="font-mono">{r.scores[query]!.map((s) => (Number.isFinite(s) ? fmt(s, 2) : "−∞")).join(", ")}</span>
            </li>
            <li>
              Softmax turns scores into weights: <span className="font-mono">{r.weights[query]!.map((w) => fmt(w, 2)).join(", ")}</span>
            </li>
            <li>
              Output = weighted average of value vectors: <span className="font-mono">{vec(r.out[query]!)}</span>
            </li>
          </ol>
          <p className="text-muted">
            Raising the sharpness makes the softmax pick one token more decisively; the causal mask sets future positions to −∞ so they get zero weight. Real models
            use learned matrices, hundreds of dimensions and many heads in parallel — these toy 2-D vectors only demonstrate the mechanism.
          </p>
        </div>
      </div>
    </div>
  );
}
