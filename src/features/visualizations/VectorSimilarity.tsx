// Two 2-D vectors you can drag or type: dot product, norms, cosine similarity,
// angle and Euclidean distance — the measures used by embedding search.
import { useRef, useState, type PointerEvent } from "react";
import { Button } from "../../components/ui";
import { fmt } from "./controls";

type Vec = [number, number];
const RANGE = 5;
const SIZE = 300;
const toPx = (v: number) => ((v + RANGE) / (2 * RANGE)) * SIZE;
const toPy = (v: number) => SIZE - ((v + RANGE) / (2 * RANGE)) * SIZE;
const fromPx = (px: number) => (px / SIZE) * 2 * RANGE - RANGE;
const fromPy = (py: number) => ((SIZE - py) / SIZE) * 2 * RANGE - RANGE;
const round = (v: number) => Math.round(v * 10) / 10;

export function similarity(a: Vec, b: Vec) {
  const dot = a[0] * b[0] + a[1] * b[1];
  const na = Math.hypot(a[0], a[1]);
  const nb = Math.hypot(b[0], b[1]);
  const cosine = na && nb ? dot / (na * nb) : NaN;
  const angle = Number.isNaN(cosine) ? NaN : (Math.acos(Math.max(-1, Math.min(1, cosine))) * 180) / Math.PI;
  const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
  return { dot, na, nb, cosine, angle, distance };
}

const presets: { label: string; a: Vec; b: Vec; note: string }[] = [
  { label: "Similar", a: [3, 1], b: [2.5, 1.5], note: "Small angle → cosine close to 1." },
  { label: "Same direction, different length", a: [1, 1], b: [4, 4], note: "Cosine is exactly 1, yet the Euclidean distance is large. Cosine ignores length." },
  { label: "Orthogonal", a: [3, 0], b: [0, 2], note: "At 90° the dot product and cosine are 0: unrelated directions." },
  { label: "Opposite", a: [2, 1], b: [-2, -1], note: "Pointing opposite ways → cosine −1." },
];

export function VectorSimilarity({ a: initialA, b: initialB }: { a: Vec; b: Vec }) {
  const [a, setA] = useState<Vec>(initialA);
  const [b, setB] = useState<Vec>(initialB);
  const [note, setNote] = useState<string | null>(null);
  const dragging = useRef<"a" | "b" | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const s = similarity(a, b);

  const move = (e: PointerEvent<SVGSVGElement>) => {
    if (!dragging.current || !svg.current) return;
    const rect = svg.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * SIZE;
    const y = ((e.clientY - rect.top) / rect.height) * SIZE;
    const v: Vec = [round(Math.max(-RANGE, Math.min(RANGE, fromPx(x)))), round(Math.max(-RANGE, Math.min(RANGE, fromPy(y))))];
    if (dragging.current === "a") setA(v);
    else setB(v);
    setNote(null);
  };

  const input = (label: string, value: number, set: (v: number) => void) => (
    <label className="flex items-center gap-1 text-[12.5px] text-muted">
      {label}
      <input
        type="number"
        step={0.5}
        min={-RANGE}
        max={RANGE}
        value={value}
        onChange={(e) => set(Math.max(-RANGE, Math.min(RANGE, Number(e.target.value) || 0)))}
        className="h-7 w-16 rounded border border-border bg-surface px-1.5 font-mono text-[12.5px] text-text"
      />
    </label>
  );

  return (
    <div className="grid gap-4 p-4 md:grid-cols-[320px_minmax(0,1fr)]">
      <div>
        <svg
          ref={svg}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="w-full touch-none select-none rounded-lg border border-border bg-code"
          onPointerMove={move}
          onPointerUp={() => (dragging.current = null)}
          onPointerLeave={() => (dragging.current = null)}
          role="img"
          aria-label={`Vector a = (${a.join(", ")}), vector b = (${b.join(", ")}). Cosine similarity ${fmt(s.cosine)}.`}
        >
          {Array.from({ length: 2 * RANGE + 1 }, (_, i) => i - RANGE).map((g) => (
            <g key={g}>
              <line x1={toPx(g)} y1={0} x2={toPx(g)} y2={SIZE} stroke="var(--gw-border)" strokeWidth={g === 0 ? 1.4 : 0.6} />
              <line x1={0} y1={toPy(g)} x2={SIZE} y2={toPy(g)} stroke="var(--gw-border)" strokeWidth={g === 0 ? 1.4 : 0.6} />
            </g>
          ))}
          <line x1={toPx(a[0])} y1={toPy(a[1])} x2={toPx(b[0])} y2={toPy(b[1])} stroke="var(--gw-faint)" strokeDasharray="4 4" />
          {(
            [
              ["a", a, "var(--gw-accent)"],
              ["b", b, "var(--gw-violet)"],
            ] as const
          ).map(([name, v, color]) => (
            <g key={name}>
              <line x1={toPx(0)} y1={toPy(0)} x2={toPx(v[0])} y2={toPy(v[1])} stroke={color} strokeWidth={3} strokeLinecap="round" />
              <circle
                cx={toPx(v[0])}
                cy={toPy(v[1])}
                r={9}
                fill={color}
                className="cursor-grab"
                onPointerDown={(e) => {
                  dragging.current = name;
                  (e.target as Element).setPointerCapture?.(e.pointerId);
                }}
              />
              <text x={toPx(v[0]) + 12} y={toPy(v[1]) - 10} fill={color} className="text-[14px] font-semibold">
                {name}
              </text>
            </g>
          ))}
        </svg>
        <div className="mt-2 flex flex-wrap gap-3">
          {input("a.x", a[0], (v) => setA([v, a[1]]))}
          {input("a.y", a[1], (v) => setA([a[0], v]))}
          {input("b.x", b[0], (v) => setB([v, b[1]]))}
          {input("b.y", b[1], (v) => setB([b[0], v]))}
        </div>
      </div>
      <div className="space-y-3 text-[14px]">
        <p className="text-muted">Drag the tips of the vectors (or type coordinates). Embedding search ranks documents by these same measures in hundreds of dimensions.</p>
        <table className="w-full text-left text-[13.5px]">
          <tbody className="divide-y divide-border">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Dot product a·b</th>
              <td className="font-mono">
                {fmt(a[0])}×{fmt(b[0])} + {fmt(a[1])}×{fmt(b[1])} = <strong>{fmt(s.dot)}</strong>
              </td>
            </tr>
            <tr>
              <th className="py-1.5 pr-3 font-medium">Lengths ‖a‖, ‖b‖</th>
              <td className="font-mono">
                {fmt(s.na)}, {fmt(s.nb)}
              </td>
            </tr>
            <tr>
              <th className="py-1.5 pr-3 font-medium">Cosine similarity</th>
              <td className="font-mono">
                a·b / (‖a‖‖b‖) = <strong className="text-accent">{fmt(s.cosine)}</strong>
              </td>
            </tr>
            <tr>
              <th className="py-1.5 pr-3 font-medium">Angle</th>
              <td className="font-mono">{fmt(s.angle, 1)}°</td>
            </tr>
            <tr>
              <th className="py-1.5 pr-3 font-medium">Euclidean distance</th>
              <td className="font-mono">{fmt(s.distance)}</td>
            </tr>
          </tbody>
        </table>
        <div className="flex flex-wrap gap-1.5">
          {presets.map((p) => (
            <Button
              key={p.label}
              size="sm"
              onClick={() => {
                setA(p.a);
                setB(p.b);
                setNote(p.note);
              }}
            >
              {p.label}
            </Button>
          ))}
        </div>
        {note && <p className="rounded-lg bg-accent-soft/60 px-3 py-2 text-[13.5px]">{note}</p>}
        <p className="text-[12.5px] text-muted">
          Cosine similarity ranges from −1 to 1 and ignores vector length; dot product grows with length; for vectors normalised to length 1, ranking by dot product
          and by cosine is identical.
        </p>
      </div>
    </div>
  );
}
