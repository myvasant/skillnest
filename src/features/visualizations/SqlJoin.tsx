// INNER / LEFT / RIGHT / FULL OUTER joins on two small tables, with the matching
// logic visible row by row. NULL keys never match (as in SQL).
import { useMemo, useState } from "react";
import { cn } from "../../components/ui";

type Cell = string | number | null;
interface Table {
  name: string;
  key: string;
  columns: string[];
  rows: Cell[][];
}
export type JoinKind = "INNER" | "LEFT" | "RIGHT" | "FULL";

export function joinTables(left: Table, right: Table, kind: JoinKind) {
  const lk = left.columns.indexOf(left.key);
  const rk = right.columns.indexOf(right.key);
  const out: { l: Cell[] | null; r: Cell[] | null; li: number | null; ri: number | null }[] = [];
  const matchedRight = new Set<number>();
  left.rows.forEach((l, li) => {
    let matched = false;
    right.rows.forEach((r, ri) => {
      if (l[lk] !== null && l[lk] === r[rk]) {
        out.push({ l, r, li, ri });
        matched = true;
        matchedRight.add(ri);
      }
    });
    if (!matched && (kind === "LEFT" || kind === "FULL")) out.push({ l, r: null, li, ri: null });
  });
  if (kind === "RIGHT" || kind === "FULL") {
    right.rows.forEach((r, ri) => {
      if (!matchedRight.has(ri)) out.push({ l: null, r, li: null, ri });
    });
  }
  if (kind === "RIGHT") {
    // Present RIGHT joins in right-table order for readability.
    out.sort((a, b) => (a.ri ?? 0) - (b.ri ?? 0));
  }
  return out;
}

const explain: Record<JoinKind, string> = {
  INNER: "Only rows whose keys match in both tables.",
  LEFT: "Every row from the left table; right-side columns are NULL where there is no match.",
  RIGHT: "Every row from the right table; left-side columns are NULL where there is no match.",
  FULL: "Every row from both tables, matched where possible, NULL-filled otherwise.",
};

function CellView({ v }: { v: Cell }) {
  return v === null ? <span className="italic text-faint">NULL</span> : <span>{v}</span>;
}

type JoinRow = ReturnType<typeof joinTables>[number];

function SourceTable({ t, side, rows, highlight }: { t: Table; side: "l" | "r"; rows: JoinRow[]; highlight: JoinRow | null | undefined }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 font-mono text-[12.5px] font-semibold">{t.name}</p>
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            {t.columns.map((c) => (
              <th key={c} className={cn("border border-border bg-surface-2 px-2 py-1 text-left font-medium", c === t.key && "text-accent")}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.rows.map((r, i) => {
            const hl = highlight && (side === "l" ? highlight.li === i : highlight.ri === i);
            const used = rows.some((x) => (side === "l" ? x.li === i : x.ri === i));
            return (
              <tr key={i} className={cn(hl && "bg-accent-soft", !used && "opacity-45")}>
                {r.map((v, j) => (
                  <td key={j} className="border border-border px-2 py-1 font-mono">
                    <CellView v={v} />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SqlJoin({ left, right }: { left: Table; right: Table }) {
  const [kind, setKind] = useState<JoinKind>("INNER");
  const [hover, setHover] = useState<number | null>(null);
  const rows = useMemo(() => joinTables(left, right, kind), [left, right, kind]);
  const h = hover !== null ? rows[hover] : null;
  const sql = `SELECT *\nFROM ${left.name}\n${kind === "INNER" ? "INNER JOIN" : kind === "FULL" ? "FULL OUTER JOIN" : `${kind} JOIN`} ${right.name}\n  ON ${left.name}.${left.key} = ${right.name}.${right.key};`;

  return (
    <div className="space-y-4 p-4">
      <div role="radiogroup" aria-label="Join type" className="inline-flex flex-wrap rounded-lg border border-border bg-surface-2 p-0.5">
        {(["INNER", "LEFT", "RIGHT", "FULL"] as JoinKind[]).map((k) => (
          <button key={k} role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className={cn("rounded-md px-3 py-1 font-mono text-[12.5px] font-medium", kind === k ? "bg-surface shadow-card" : "text-muted")}>
            {k === "FULL" ? "FULL OUTER" : k}
          </button>
        ))}
      </div>
      <p className="text-[14px]">{explain[kind]}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <SourceTable t={left} side="l" rows={rows} highlight={h} />
        <SourceTable t={right} side="r" rows={rows} highlight={h} />
      </div>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_240px]">
        <div className="min-w-0 overflow-x-auto">
          <p className="mb-1 text-[12.5px] font-semibold">
            Result <span className="font-normal text-muted">({rows.length} rows — hover a row to see where it came from)</span>
          </p>
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr>
                {left.columns.map((c) => (
                  <th key={`l-${c}`} className="border border-border bg-info-soft px-2 py-1 text-left font-medium">
                    {left.name}.{c}
                  </th>
                ))}
                {right.columns.map((c) => (
                  <th key={`r-${c}`} className="border border-border bg-violet-soft px-2 py-1 text-left font-medium">
                    {right.name}.{c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} tabIndex={0} className={cn(hover === i && "bg-accent-soft")}>
                  {left.columns.map((_, j) => (
                    <td key={`l-${j}`} className="border border-border px-2 py-1 font-mono">
                      <CellView v={row.l ? row.l[j]! : null} />
                    </td>
                  ))}
                  {right.columns.map((_, j) => (
                    <td key={`r-${j}`} className="border border-border px-2 py-1 font-mono">
                      <CellView v={row.r ? row.r[j]! : null} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <pre className="h-fit rounded-lg border border-border bg-code px-3 py-2 font-mono text-[12.5px] leading-relaxed">{sql}</pre>
      </div>
      <p className="text-[12.5px] text-muted">Faded source rows do not appear in the result. NULL keys never match anything — not even another NULL.</p>
    </div>
  );
}
