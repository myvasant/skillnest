// A tiny network (inputs → 2 hidden neurons → 1 output) with adjustable weights.
// Each neuron shows z = w·x + b and its activation a = g(z).
import { useState } from "react";
import { cn } from "../../components/ui";
import { fmt } from "./controls";

type Act = "relu" | "sigmoid" | "tanh" | "linear";
const acts: Record<Act, (z: number) => number> = {
  relu: (z) => Math.max(0, z),
  sigmoid: (z) => 1 / (1 + Math.exp(-z)),
  tanh: (z) => Math.tanh(z),
  linear: (z) => z,
};

export function forward(x: number[], W1: number[][], b1: number[], W2: number[], b2: number, hiddenAct: Act) {
  const z1 = W1.map((row, j) => row.reduce((s, w, i) => s + w * (x[i] ?? 0), 0) + b1[j]!);
  const a1 = z1.map(acts[hiddenAct]);
  const z2 = W2.reduce((s, w, j) => s + w * a1[j]!, 0) + b2;
  return { z1, a1, z2, out: acts.sigmoid(z2) };
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center gap-2 text-[12.5px]">
      <span className="w-14 font-mono text-muted">{label}</span>
      <input type="range" min={-3} max={3} step={0.1} value={value} onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-[var(--gw-accent)]" aria-label={label} />
      <span className="w-10 text-right font-mono tabular-nums">{value.toFixed(1)}</span>
    </label>
  );
}

export function NeuralForward({ inputs }: { inputs: number[] }) {
  const n = inputs.length;
  const [x, setX] = useState(inputs);
  const [W1, setW1] = useState<number[][]>([Array.from({ length: n }, (_, i) => (i % 2 ? -1 : 1)), Array.from({ length: n }, () => 0.5)]);
  const [b1, setB1] = useState([0, -0.5]);
  const [W2, setW2] = useState([1.5, -1]);
  const [b2, setB2] = useState(0);
  const [act, setAct] = useState<Act>("relu");
  const r = forward(x, W1, b1, W2, b2, act);

  const H = 70 + Math.max(n, 2) * 70;
  const inY = (i: number) => (H / (n + 1)) * (i + 1);
  const hY = (j: number) => (H / 3) * (j + 1);
  const outY = H / 2;
  const edge = (w: number) => ({ stroke: w >= 0 ? "var(--gw-accent)" : "var(--gw-danger)", strokeWidth: 0.8 + Math.min(Math.abs(w), 3) * 1.4, opacity: 0.25 + Math.min(Math.abs(w), 3) / 4 });

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div>
        <svg viewBox={`0 0 460 ${H}`} className="w-full" role="img" aria-label={`Network output ${fmt(r.out)}`}>
          {x.map((_, i) => [0, 1].map((j) => <line key={`${i}-${j}`} x1={60} y1={inY(i)} x2={230} y2={hY(j)} {...edge(W1[j]![i]!)} />))}
          {[0, 1].map((j) => <line key={`h${j}`} x1={230} y1={hY(j)} x2={400} y2={outY} {...edge(W2[j]!)} />)}
          {x.map((v, i) => (
            <g key={i}>
              <circle cx={60} cy={inY(i)} r={24} fill="var(--gw-surface-2)" stroke="var(--gw-border-strong)" />
              <text x={60} y={inY(i) + 4} textAnchor="middle" className="text-[12px] font-mono" fill="var(--gw-text)">
                {fmt(v, 2)}
              </text>
              <text x={60} y={inY(i) - 30} textAnchor="middle" className="text-[11px]" fill="var(--gw-muted)">
                x{i + 1}
              </text>
            </g>
          ))}
          {[0, 1].map((j) => (
            <g key={j}>
              <circle cx={230} cy={hY(j)} r={30} fill="var(--gw-accent-soft)" stroke="var(--gw-accent)" />
              <text x={230} y={hY(j) - 4} textAnchor="middle" className="text-[10.5px] font-mono" fill="var(--gw-muted)">
                z={fmt(r.z1[j]!, 2)}
              </text>
              <text x={230} y={hY(j) + 11} textAnchor="middle" className="text-[12px] font-mono font-semibold" fill="var(--gw-text)">
                a={fmt(r.a1[j]!, 2)}
              </text>
            </g>
          ))}
          <circle cx={400} cy={outY} r={32} fill="var(--gw-violet-soft)" stroke="var(--gw-violet)" />
          <text x={400} y={outY - 4} textAnchor="middle" className="text-[10.5px] font-mono" fill="var(--gw-muted)">
            z={fmt(r.z2, 2)}
          </text>
          <text x={400} y={outY + 12} textAnchor="middle" className="text-[13px] font-mono font-semibold" fill="var(--gw-text)">
            {fmt(r.out, 3)}
          </text>
        </svg>
        <p className="mt-2 text-[13px] text-muted">
          Edge colour shows sign (teal positive, red negative) and thickness shows magnitude. The output neuron uses a sigmoid, so it can be read as a probability.
        </p>
      </div>
      <div className="space-y-3">
        <div role="radiogroup" aria-label="Hidden activation" className="inline-flex flex-wrap rounded-lg border border-border bg-surface-2 p-0.5">
          {(Object.keys(acts) as Act[]).map((a) => (
            <button key={a} role="radio" aria-checked={act === a} onClick={() => setAct(a)} className={cn("rounded-md px-2.5 py-1 font-mono text-[12px]", act === a ? "bg-surface shadow-card" : "text-muted")}>
              {a}
            </button>
          ))}
        </div>
        <fieldset className="space-y-1">
          <legend className="text-[12px] font-semibold uppercase tracking-wide text-muted">Inputs</legend>
          {x.map((v, i) => (
            <Slider key={i} label={`x${i + 1}`} value={v} onChange={(nv) => setX((xs) => xs.map((q, k) => (k === i ? nv : q)))} />
          ))}
        </fieldset>
        <fieldset className="space-y-1">
          <legend className="text-[12px] font-semibold uppercase tracking-wide text-muted">Hidden layer</legend>
          {[0, 1].map((j) => (
            <div key={j} className="space-y-1">
              {x.map((_, i) => (
                <Slider key={i} label={`w${j + 1}${i + 1}`} value={W1[j]![i]!} onChange={(nv) => setW1((W) => W.map((row, rj) => (rj === j ? row.map((q, ri) => (ri === i ? nv : q)) : row)))} />
              ))}
              <Slider label={`b${j + 1}`} value={b1[j]!} onChange={(nv) => setB1((b) => b.map((q, k) => (k === j ? nv : q)))} />
            </div>
          ))}
        </fieldset>
        <fieldset className="space-y-1">
          <legend className="text-[12px] font-semibold uppercase tracking-wide text-muted">Output</legend>
          {[0, 1].map((j) => (
            <Slider key={j} label={`v${j + 1}`} value={W2[j]!} onChange={(nv) => setW2((w) => w.map((q, k) => (k === j ? nv : q)))} />
          ))}
          <Slider label="b_out" value={b2} onChange={setB2} />
        </fieldset>
        <p className="rounded-lg bg-surface-2 px-3 py-2 font-mono text-[12px] leading-relaxed">
          z₁ = {W1[0]!.map((w, i) => `${w.toFixed(1)}·${fmt(x[i]!, 2)}`).join(" + ")} + {b1[0]!.toFixed(1)} = {fmt(r.z1[0]!, 3)}
          <br />
          a₁ = {act}(z₁) = {fmt(r.a1[0]!, 3)}
        </p>
        <p className="text-[12.5px] text-muted">
          Try the <span className="font-mono">linear</span> activation: the network can then only compute a weighted sum of its inputs, however many layers it has.
        </p>
      </div>
    </div>
  );
}
