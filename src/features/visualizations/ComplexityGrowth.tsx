// How operation counts grow for common complexity classes as n increases.
import { useState } from "react";
import { cn } from "../../components/ui";

export const classes = [
  { id: "1", label: "O(1)", f: () => 1, color: "var(--gw-success)", example: "dict lookup, list index" },
  { id: "logn", label: "O(log n)", f: (n: number) => Math.max(1, Math.log2(n)), color: "var(--gw-info)", example: "binary search" },
  { id: "n", label: "O(n)", f: (n: number) => n, color: "var(--gw-accent)", example: "loop over a list, x in list" },
  { id: "nlogn", label: "O(n log n)", f: (n: number) => n * Math.max(1, Math.log2(n)), color: "var(--gw-violet)", example: "sorted(), merge sort" },
  { id: "n2", label: "O(n²)", f: (n: number) => n * n, color: "var(--gw-warning)", example: "nested loops over the same list" },
  { id: "2n", label: "O(2ⁿ)", f: (n: number) => 2 ** n, color: "var(--gw-danger)", example: "all subsets, naive recursive Fibonacci" },
] as const;

const W = 520;
const H = 240;

export function ComplexityGrowth({ maxN }: { maxN: number }) {
  const [n, setN] = useState(Math.min(16, maxN));
  const [log, setLog] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const values = classes.map((c) => ({ ...c, v: c.f(n) }));
  const maxY = Math.max(...classes.filter((c) => !hidden.has(c.id)).map((c) => c.f(maxN)), 2);
  const y = (v: number) => (log ? H - (Math.log10(Math.max(v, 1)) / Math.log10(maxY)) * H : H - (Math.min(v, maxY) / maxY) * H);
  const x = (i: number) => ((i - 1) / Math.max(1, maxN - 1)) * W;
  const fmtBig = (v: number) => (v >= 1e9 ? `${(v / 1e9).toFixed(1)} billion` : v >= 1e6 ? `${(v / 1e6).toFixed(1)} million` : Math.round(v).toLocaleString());

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-[14px]">
          n =
          <input type="range" min={1} max={maxN} value={n} onChange={(e) => setN(Number(e.target.value))} className="accent-[var(--gw-accent)]" aria-label="Input size n" />
          <span className="w-8 font-mono tabular-nums">{n}</span>
        </label>
        <label className="flex items-center gap-1.5 text-[13px] text-muted">
          <input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} className="accent-[var(--gw-accent)]" />
          logarithmic y-axis
        </label>
      </div>
      <svg viewBox={`-30 -10 ${W + 40} ${H + 30}`} className="w-full" role="img" aria-label={`Growth curves up to n = ${maxN}; current n = ${n}`}>
        <line x1={0} y1={H} x2={W} y2={H} stroke="var(--gw-border-strong)" />
        <line x1={0} y1={0} x2={0} y2={H} stroke="var(--gw-border-strong)" />
        <text x={W} y={H + 18} textAnchor="end" className="text-[11px]" fill="var(--gw-muted)">
          n →
        </text>
        <text x={-6} y={4} textAnchor="end" className="text-[11px]" fill="var(--gw-muted)">
          ops
        </text>
        {classes
          .filter((c) => !hidden.has(c.id))
          .map((c) => {
            const pts = Array.from({ length: maxN }, (_, i) => `${x(i + 1)},${Math.max(0, y(c.f(i + 1)))}`).join(" ");
            return <polyline key={c.id} points={pts} fill="none" stroke={c.color} strokeWidth={2.2} />;
          })}
        <line x1={x(n)} y1={0} x2={x(n)} y2={H} stroke="var(--gw-faint)" strokeDasharray="3 3" />
      </svg>
      <table className="w-full text-left text-[13.5px]">
        <thead className="text-[12px] text-muted">
          <tr>
            <th className="pb-1 font-medium">Class</th>
            <th className="pb-1 font-medium">Operations at n = {n}</th>
            <th className="pb-1 font-medium">Typical example</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {values.map((c) => (
            <tr key={c.id} className={cn(hidden.has(c.id) && "opacity-40")}>
              <td className="py-1.5">
                <button
                  className="flex items-center gap-2 font-mono font-medium"
                  onClick={() =>
                    setHidden((h) => {
                      const next = new Set(h);
                      if (next.has(c.id)) next.delete(c.id);
                      else next.add(c.id);
                      return next;
                    })
                  }
                  aria-pressed={!hidden.has(c.id)}
                  title="Show/hide on the chart"
                >
                  <span className="inline-block size-2.5 rounded-full" style={{ background: c.color }} aria-hidden />
                  {c.label}
                </button>
              </td>
              <td className="font-mono tabular-nums">{fmtBig(c.v)}</td>
              <td className="text-muted">{c.example}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[13px] text-muted">
        At a billion simple operations per second, O(2ⁿ) at n = 50 would take about {fmtBig(2 ** 50 / 1e9 / 86400)} days, while O(n log n) at n = 1,000,000 takes
        about 20 milliseconds. Big-O ignores constant factors, so always measure when the classes are equal.
      </p>
    </div>
  );
}
