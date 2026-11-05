// Data-driven, step-by-step diagram: lessons describe nodes, edges and steps in
// YAML (HTTP lifecycles, RAG pipelines, agent loops, CI/CD...). Each step lights
// up the nodes/edges involved and explains what happens.
import { useMemo } from "react";
import type { z } from "zod";
import { visualizationSchemas } from "../../content/visualizationSchemas";
import { Markdown } from "../../components/Markdown";
import { cn } from "../../components/ui";
import { StepControls, useStepper } from "./controls";

type Props = z.infer<(typeof visualizationSchemas)["step-diagram"]>;

const NODE_W = 132;
const NODE_H = 46;

export function StepDiagram({ width, height, nodes, edges, steps }: Props) {
  const stepper = useStepper(steps.length, 2200);
  const step = steps[stepper.index]!;
  const active = useMemo(() => new Set(step.active), [step]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  return (
    <div>
      <div className="border-b border-border bg-surface-2/40 px-2 py-2">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={`Diagram, step ${stepper.index + 1}: ${step.title}`}>
          <defs>
            <marker id="sd-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-border-strong)" />
            </marker>
            <marker id="sd-arrow-on" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-accent)" />
            </marker>
          </defs>
          {edges.map((e) => {
            const a = byId.get(e.from);
            const b = byId.get(e.to);
            if (!a || !b) return null;
            const on = active.has(e.id);
            // Start and end the arrow where the centre-to-centre line leaves each box.
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const clip = (cx: number, cy: number, ux: number, uy: number) => {
              const t = Math.min(ux ? NODE_W / 2 / Math.abs(ux) : Infinity, uy ? NODE_H / 2 / Math.abs(uy) : Infinity, 0.5) * 1.04;
              return [cx + ux * t, cy + uy * t] as const;
            };
            const [x1, y1] = clip(a.x, a.y, dx, dy);
            const [x2, y2] = clip(b.x, b.y, -dx, -dy);
            return (
              <g key={e.id} opacity={step.active.length && !on ? 0.35 : 1}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={on ? "var(--gw-accent)" : "var(--gw-border-strong)"} strokeWidth={on ? 2.4 : 1.4} markerEnd={on ? "url(#sd-arrow-on)" : "url(#sd-arrow)"} />
                {e.label && (
                  <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 6} textAnchor="middle" className="text-[11px]" fill={on ? "var(--gw-accent)" : "var(--gw-muted)"} style={{ fontWeight: on ? 600 : 400 }}>
                    {e.label}
                  </text>
                )}
              </g>
            );
          })}
          {nodes.map((n) => {
            const on = active.has(n.id);
            const dim = step.active.length > 0 && !on;
            const x = n.x - NODE_W / 2;
            const y = n.y - NODE_H / 2;
            const stroke = on ? "var(--gw-accent)" : "var(--gw-border-strong)";
            const fill = on ? "var(--gw-accent-soft)" : "var(--gw-surface)";
            return (
              <g key={n.id} opacity={dim ? 0.45 : 1}>
                {n.shape === "store" ? (
                  <>
                    <path d={`M${x},${y + 8} v${NODE_H - 16} a${NODE_W / 2},8 0 0 0 ${NODE_W},0 v-${NODE_H - 16}`} fill={fill} stroke={stroke} strokeWidth={on ? 2 : 1.2} />
                    <ellipse cx={n.x} cy={y + 8} rx={NODE_W / 2} ry={8} fill={fill} stroke={stroke} strokeWidth={on ? 2 : 1.2} />
                  </>
                ) : n.shape === "actor" ? (
                  <>
                    <circle cx={n.x} cy={y + 6} r={7} fill={fill} stroke={stroke} strokeWidth={on ? 2 : 1.2} />
                    <rect x={x + 26} y={y + 16} width={NODE_W - 52} height={NODE_H - 16} rx={12} fill={fill} stroke={stroke} strokeWidth={on ? 2 : 1.2} />
                  </>
                ) : (
                  <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={n.shape === "pill" ? NODE_H / 2 : 9} fill={fill} stroke={stroke} strokeWidth={on ? 2 : 1.2} />
                )}
                <text x={n.x} y={n.shape === "actor" ? y + 36 : n.y + 4} textAnchor="middle" className="text-[12.5px]" fill="var(--gw-text)" style={{ fontWeight: on ? 650 : 500 }}>
                  {n.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="grid gap-0 md:grid-cols-[minmax(0,1fr)_220px]">
        <div className="space-y-3 p-4" aria-live="polite">
          <StepControls stepper={stepper} total={steps.length} />
          <h4 className="text-[15px] font-semibold">{step.title}</h4>
          <Markdown className="text-[14.5px]">{step.body}</Markdown>
          {step.payload && (
            <pre className="scrollbar-thin overflow-x-auto rounded-lg border border-border bg-code px-3 py-2 font-mono text-[12.5px] leading-relaxed">{step.payload}</pre>
          )}
        </div>
        <ol className="border-t border-border p-3 text-[13px] md:border-l md:border-t-0" aria-label="All steps">
          {steps.map((s, i) => (
            <li key={i}>
              <button
                onClick={() => stepper.setIndex(i)}
                aria-current={i === stepper.index ? "step" : undefined}
                className={cn("flex w-full gap-2 rounded-md px-2 py-1 text-left", i === stepper.index ? "bg-accent-soft font-medium text-text" : "text-muted hover:bg-surface-2")}
              >
                <span className="w-4 shrink-0 text-right tabular-nums text-faint">{i + 1}</span>
                <span>{s.title}</span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
