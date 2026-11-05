// Interactive prerequisite graph for one stage (or any concept subset).
// Nodes are real links (keyboard focusable); hovering or focusing a node
// highlights everything it depends on and everything that depends on it.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { curriculum } from "../../content/runtime";
import { ancestors, layeredLayout } from "../../engine/layout";
import type { ConceptMastery } from "../../engine/mastery";
import { statusColor, statusLabel } from "./status";

const W = 210;
const H = 52;

export function ConceptGraph({ conceptIds, mastery, filtered }: { conceptIds: string[]; mastery: Record<string, ConceptMastery>; filtered?: Set<string> }) {
  const navigate = useNavigate();
  const [focus, setFocus] = useState<string | null>(null);
  const layout = useMemo(() => {
    const edges: [string, string][] = [];
    for (const id of conceptIds) for (const r of curriculum.concepts[id]!.requires) edges.push([r, id]);
    return layeredLayout({ ids: conceptIds, edges }, { nodeWidth: W, nodeHeight: H, colGap: 64, rowGap: 14, pad: 16 });
  }, [conceptIds]);

  const related = useMemo(() => {
    if (!focus) return null;
    const up = ancestors(focus, (id) => curriculum.concepts[id]?.requires ?? []);
    const down = ancestors(focus, (id) => curriculum.concepts[id]?.requiredBy ?? []);
    return new Set([focus, ...up, ...down]);
  }, [focus]);

  return (
    <div
      className="scrollbar-thin max-h-[72vh] overflow-auto rounded-xl border border-border bg-surface"
      role="group"
      aria-label="Prerequisite graph. Each node links to its lesson or concept page."
    >
      <svg width={layout.width} height={layout.height} className="block" style={{ minWidth: layout.width }}>
        <defs>
          <marker id="cg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-border-strong)" />
          </marker>
          <marker id="cg-arrow-hot" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-accent)" />
          </marker>
        </defs>
        {layout.edges.map(([a, b]) => {
          const from = layout.nodes[a]!;
          const to = layout.nodes[b]!;
          const x1 = from.x + W;
          const y1 = from.y + H / 2;
          const x2 = to.x - 2;
          const y2 = to.y + H / 2;
          const hot = related ? related.has(a) && related.has(b) : false;
          const dim = related && !hot;
          return (
            <path
              key={`${a}->${b}`}
              d={`M ${x1} ${y1} C ${x1 + 36} ${y1}, ${x2 - 36} ${y2}, ${x2} ${y2}`}
              fill="none"
              stroke={hot ? "var(--gw-accent)" : "var(--gw-border-strong)"}
              strokeWidth={hot ? 2 : 1.2}
              opacity={dim ? 0.25 : 1}
              markerEnd={hot ? "url(#cg-arrow-hot)" : "url(#cg-arrow)"}
            />
          );
        })}
        {conceptIds.map((id) => {
          const n = layout.nodes[id]!;
          const c = curriculum.concepts[id]!;
          const m = mastery[id]!;
          const dim = (related && !related.has(id)) || (filtered && !filtered.has(id));
          const external = c.requires.filter((r) => !conceptIds.includes(r)).length;
          const href = c.lessonId ? `/learn/${c.lessonId}` : `/concept/${id}`;
          return (
            <a
              key={id}
              href={href}
              onClick={(e) => {
                e.preventDefault();
                navigate(href);
              }}
              onMouseEnter={() => setFocus(id)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(id)}
              onBlur={() => setFocus(null)}
              aria-label={`${c.title}. ${statusLabel(m)}. ${c.lessonId ? "Lesson available." : "Outline only."} ${c.requires.length} prerequisites.`}
              style={{ opacity: dim ? 0.3 : 1 }}
              className="cursor-pointer focus:outline-none [&:focus>rect.frame]:stroke-[var(--gw-accent)] [&:focus>rect.frame]:stroke-2"
            >
              <rect
                className="frame"
                x={n.x}
                y={n.y}
                width={W}
                height={H}
                rx={9}
                fill="var(--gw-surface)"
                stroke={focus === id ? "var(--gw-accent)" : "var(--gw-border)"}
                strokeWidth={focus === id ? 2 : 1}
              />
              <rect x={n.x} y={n.y} width={4} height={H} rx={2} fill={statusColor[m.status]} />
              <foreignObject x={n.x + 10} y={n.y + 4} width={W - 16} height={H - 8}>
                <div className="flex h-full flex-col justify-center leading-tight">
                  <span className="line-clamp-2 text-[12.5px] font-medium text-text">{c.title}</span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted">
                    {c.lessonId ? <span className="font-semibold text-accent">Lesson</span> : <span>Outline</span>}
                    <span>· {c.level}</span>
                    {external > 0 && <span title="Prerequisites in other stages">· +{external} ext.</span>}
                  </span>
                </div>
              </foreignObject>
            </a>
          );
        })}
      </svg>
    </div>
  );
}
