// Gradient descent on f(x) = (x - target)², whose derivative is 2(x - target).
// Shows each update x ← x − η·f'(x), and what too-large learning rates do.
import { useMemo, useState } from "react";
import { fmt, StepControls, useStepper } from "./controls";

export function descend(start: number, target: number, lr: number, steps = 25) {
  const out: { x: number; f: number; grad: number }[] = [];
  let x = start;
  for (let i = 0; i <= steps; i++) {
    const grad = 2 * (x - target);
    out.push({ x, f: (x - target) ** 2, grad });
    x = x - lr * grad;
    if (!Number.isFinite(x) || Math.abs(x) > 1e6) break;
  }
  return out;
}

const W = 520;
const H = 240;

export function GradientDescent({ target, start, learningRate }: { target: number; start: number; learningRate: number }) {
  const [lr, setLr] = useState(learningRate);
  const path = useMemo(() => descend(start, target, lr), [start, target, lr]);
  const stepper = useStepper(path.length, 700);
  const i = Math.min(stepper.index, path.length - 1);
  const p = path[i]!;
  const span = Math.max(Math.abs(start - target) * 1.6, 4);
  const lo = target - span;
  const hi = target + span;
  const fMax = span * span;
  const sx = (x: number) => ((Math.max(lo, Math.min(hi, x)) - lo) / (hi - lo)) * W;
  const sy = (f: number) => H - (Math.min(f, fMax) / fMax) * (H - 10);
  const curve = Array.from({ length: 101 }, (_, k) => lo + ((hi - lo) * k) / 100)
    .map((x) => `${sx(x)},${sy((x - target) ** 2)}`)
    .join(" ");
  const behaviour =
    lr <= 0 ? "" : lr < 0.5 ? "Converges smoothly: each step moves part of the way to the minimum." : lr === 0.5 ? "Jumps straight to the minimum in one step (only for this simple function)." : lr < 1 ? "Overshoots and oscillates around the minimum, but still converges." : lr === 1 ? "Bounces between two points forever: never converges." : "Diverges: every step overshoots further than the last.";

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-[14px]">
          learning rate η
          <input
            type="range"
            min={0.02}
            max={1.1}
            step={0.02}
            value={lr}
            onChange={(e) => {
              setLr(Number(e.target.value));
              stepper.reset();
            }}
            className="accent-[var(--gw-accent)]"
            aria-label="Learning rate"
          />
          <span className="w-12 font-mono tabular-nums">{lr.toFixed(2)}</span>
        </label>
        <span className="text-[13px] text-muted">{behaviour}</span>
      </div>
      <svg viewBox={`-10 -10 ${W + 20} ${H + 30}`} className="w-full" role="img" aria-label={`Step ${i}: x = ${fmt(p.x)}, loss = ${fmt(p.f)}`}>
        <polyline points={curve} fill="none" stroke="var(--gw-border-strong)" strokeWidth={2} />
        <line x1={sx(target)} y1={0} x2={sx(target)} y2={H} stroke="var(--gw-success)" strokeDasharray="4 4" />
        <text x={sx(target) + 4} y={12} className="text-[11px]" fill="var(--gw-success)">
          minimum at x = {target}
        </text>
        {path.slice(0, i + 1).map((q, k) =>
          k === 0 ? null : <line key={k} x1={sx(path[k - 1]!.x)} y1={sy(path[k - 1]!.f)} x2={sx(q.x)} y2={sy(q.f)} stroke="var(--gw-accent)" strokeWidth={1.5} opacity={0.6} />,
        )}
        {path.slice(0, i + 1).map((q, k) => (
          <circle key={k} cx={sx(q.x)} cy={sy(q.f)} r={k === i ? 7 : 3.5} fill={k === i ? "var(--gw-accent)" : "var(--gw-accent-soft)"} stroke="var(--gw-accent)" />
        ))}
        <text x={W / 2} y={H + 20} textAnchor="middle" className="text-[11px]" fill="var(--gw-muted)">
          x
        </text>
      </svg>
      <StepControls stepper={stepper} total={path.length} />
      <div className="grid gap-3 text-[13.5px] md:grid-cols-2">
        <table className="w-full">
          <tbody className="divide-y divide-border font-mono">
            <tr>
              <th className="py-1 pr-3 text-left font-sans font-medium">step</th>
              <td>{i}</td>
            </tr>
            <tr>
              <th className="py-1 pr-3 text-left font-sans font-medium">x</th>
              <td>{fmt(p.x)}</td>
            </tr>
            <tr>
              <th className="py-1 pr-3 text-left font-sans font-medium">loss f(x) = (x − {target})²</th>
              <td>{fmt(p.f)}</td>
            </tr>
            <tr>
              <th className="py-1 pr-3 text-left font-sans font-medium">gradient f′(x) = 2(x − {target})</th>
              <td>{fmt(p.grad)}</td>
            </tr>
          </tbody>
        </table>
        <p className="rounded-lg bg-surface-2 px-3 py-2">
          Update rule: <span className="font-mono">x ← x − η · f′(x)</span>
          <br />
          <span className="font-mono">
            {fmt(p.x)} − {lr.toFixed(2)} × {fmt(p.grad)} = {fmt(p.x - lr * p.grad)}
          </span>
          <br />
          <span className="text-muted">The gradient points uphill, so we step the opposite way. Its size shrinks near the minimum, so steps shrink too.</span>
        </p>
      </div>
    </div>
  );
}
