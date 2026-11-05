// Step through a Python program: highlighted line, call frames, names with
// arrows to the objects they refer to, and the output so far. The trace is
// produced by sys.settrace inside Pyodide (python/gw_runner.py), so what you
// see is what CPython actually did — not an animation of what it might do.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, ScanSearch } from "lucide-react";
import { CodeView } from "../../components/CodeView";
import { Badge, Button, cn } from "../../components/ui";
import { python } from "../../python/client";
import type { HeapObject, TraceResult, TraceStep } from "../../python/types";
import { RunOutput } from "../code/RunOutput";

interface Props {
  code: string;
  stdin?: string;
  showPrimitivesAsObjects?: boolean;
  maxSteps?: number;
  embedded?: boolean;
  title?: string;
}

type Arrow = { key: string; d: string; fresh: boolean };

function describeStep(step: TraceStep, index: number, total: number, ret?: HeapObject): string {
  const last = index === total - 1;
  switch (step.event) {
    case "call":
      return `Calling ${step.stack.at(-1)?.name}() — a new frame is created for its local names.`;
    case "return":
      if (step.stack.length <= 1) return last ? "The program has finished." : "Returning from the module.";
      return `${step.stack.at(-1)?.name}() returns ${ret?.repr ?? "a value"} to its caller; its frame is discarded.`;
    case "yield":
      return `${step.stack.at(-1)?.name}() yields ${ret?.repr ?? "a value"} and pauses. Its frame and local names are kept, so the next call to next() resumes right after the yield.`;
    case "exception":
      return `${step.exception?.type} raised on line ${step.line}: ${step.exception?.message}`;
    default:
      return `Next line to run: ${step.line}`;
  }
}

function changedNames(prev: TraceStep | undefined, step: TraceStep): Set<string> {
  const out = new Set<string>();
  step.stack.forEach((frame, fi) => {
    const before = prev?.stack[fi];
    for (const v of frame.vars) {
      const old = before?.name === frame.name ? before.vars.find((x) => x.name === v.name) : undefined;
      if (!old || old.ref !== v.ref) out.add(`${fi}:${v.name}`);
    }
  });
  return out;
}

export function PythonTracer({ code, stdin, showPrimitivesAsObjects = true, maxSteps = 300, embedded = false, title }: Props) {
  const [trace, setTrace] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [primitivesAsObjects, setPrimitivesAsObjects] = useState(showPrimitivesAsObjects);
  const [arrows, setArrows] = useState<Arrow[]>([]);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const stateRef = useRef<HTMLDivElement>(null);
  const anchors = useRef(new Map<string, HTMLElement>());

  const start = useCallback(async () => {
    setLoading(true);
    const result = await python.trace(code, { stdin, maxSteps });
    setTrace(result);
    setIndex(0);
    setLoading(false);
  }, [code, stdin, maxSteps]);

  // Re-trace automatically when the code changes after the first run.
  useEffect(() => {
    if (trace) void start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const steps = trace?.steps ?? [];
  const step = steps[index];
  const prev = index > 0 ? steps[index - 1] : undefined;
  const fresh = useMemo(() => (step ? changedNames(prev, step) : new Set<string>()), [step, prev]);

  useEffect(() => {
    if (!playing) return;
    if (index >= steps.length - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setIndex((i) => i + 1), 900);
    return () => clearTimeout(t);
  }, [playing, index, steps.length]);

  // Visible heap objects in a stable order: by first reference from frames.
  const objects = useMemo(() => {
    if (!step) return [] as [string, HeapObject][];
    const order: string[] = [];
    const visit = (ref: number, depth: number) => {
      const key = String(ref);
      const obj = step.heap[key];
      if (!obj || order.includes(key)) return;
      if (obj.kind === "primitive" && !primitivesAsObjects && depth === 0) return;
      order.push(key);
      if (depth > 2) return;
      obj.items?.forEach((r) => {
        const child = step.heap[String(r)];
        if (child && child.kind !== "primitive") visit(r, depth + 1);
      });
      obj.entries?.forEach(([, v]) => {
        const child = step.heap[String(v)];
        if (child && child.kind !== "primitive") visit(v, depth + 1);
      });
      obj.attrs?.forEach(([, v]) => {
        const child = step.heap[String(v)];
        if (child && child.kind !== "primitive") visit(v, depth + 1);
      });
    };
    step.stack.forEach((f) => f.vars.forEach((v) => visit(v.ref, 0)));
    if (step.returnRef !== undefined) visit(step.returnRef, 0);
    return order.map((k) => [k, step.heap[k]!] as [string, HeapObject]);
  }, [step, primitivesAsObjects]);

  const prevObjectKeys = useMemo(() => new Set(Object.keys(prev?.heap ?? {})), [prev]);

  const setAnchor = (key: string) => (el: HTMLElement | null) => {
    if (el) anchors.current.set(key, el);
    else anchors.current.delete(key);
  };

  // Measure anchor positions and draw arrows from names to objects.
  useLayoutEffect(() => {
    const container = stateRef.current;
    if (!container || !step) {
      setArrows([]);
      return;
    }
    const measure = () => {
      const base = container.getBoundingClientRect();
      const out: Arrow[] = [];
      step.stack.forEach((frame, fi) =>
        frame.vars.forEach((v) => {
          const from = anchors.current.get(`var:${fi}:${v.name}`);
          const to = anchors.current.get(`obj:${v.ref}`);
          if (!from || !to) return;
          const a = from.getBoundingClientRect();
          const b = to.getBoundingClientRect();
          const x1 = a.right - base.left;
          const y1 = a.top + a.height / 2 - base.top;
          const x2 = b.left - base.left - 2;
          const y2 = b.top + Math.min(16, b.height / 2) - base.top;
          const dx = Math.max(30, (x2 - x1) / 2);
          out.push({ key: `${fi}:${v.name}`, d: `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`, fresh: fresh.has(`${fi}:${v.name}`) });
        }),
      );
      setArrows(out);
      setBox({ w: container.scrollWidth, h: container.scrollHeight });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    return () => ro.disconnect();
  }, [step, objects, fresh]);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!steps.length) return;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, steps.length - 1));
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    }
  };

  const renderValue = (ref: number) => {
    const obj = step?.heap[String(ref)];
    if (!obj) return <span className="text-faint">?</span>;
    if (obj.kind === "primitive") return <span className="font-mono">{obj.repr}</span>;
    return <span className="font-mono text-info">#{ref}</span>;
  };

  const stdoutSoFar = trace && step ? trace.stdout.slice(0, step.stdoutLength) : "";
  const returnObj = step?.returnRef !== undefined ? step.heap[String(step.returnRef)] : undefined;

  const body = (
    <div className="text-sm" onKeyDown={onKey}>
      {!trace && (
        <div className="flex flex-col gap-3 p-4 md:flex-row md:items-start">
          <div className="min-w-0 flex-1 overflow-hidden rounded-lg border border-border">
            <CodeView code={code} />
          </div>
          <div className="md:w-64">
            <p className="mb-3 text-[13.5px] text-muted">Run the program one step at a time and watch names attach to objects.</p>
            <Button variant="primary" onClick={start} loading={loading} icon={<ScanSearch className="size-4" aria-hidden />}>
              Start step-through
            </Button>
          </div>
        </div>
      )}
      {trace && (
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div className="min-w-0 border-b border-border lg:border-r lg:border-b-0">
            <CodeView
              code={code}
              activeLine={step && !(step.event === "return" && step.stack.length <= 1) ? step.line : null}
              errorLine={step?.event === "exception" ? step.line : null}
            />
            <div className="border-t border-border px-3 py-2.5" role="group" aria-label="Step controls" tabIndex={0}>
              <div className="flex flex-wrap items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => setIndex(0)} disabled={index === 0} aria-label="First step">
                  <ChevronFirst className="size-4" aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setIndex((i) => Math.max(0, i - 1))}
                  disabled={index === 0}
                  icon={<ChevronLeft className="size-4" aria-hidden />}
                >
                  Back
                </Button>
                <Button size="sm" variant="primary" onClick={() => setIndex((i) => Math.min(steps.length - 1, i + 1))} disabled={index >= steps.length - 1}>
                  Next <ChevronRight className="size-4" aria-hidden />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setIndex(steps.length - 1)} disabled={index >= steps.length - 1} aria-label="Last step">
                  <ChevronLast className="size-4" aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? "Pause" : "Play automatically"}
                  disabled={!steps.length}
                >
                  {playing ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
                </Button>
                <Button size="sm" variant="ghost" onClick={start} aria-label="Re-run trace" title="Re-run">
                  <RotateCcw className="size-4" aria-hidden />
                </Button>
                <span className="ml-auto text-[12px] tabular-nums text-muted">
                  Step {steps.length ? index + 1 : 0} / {steps.length}
                  {trace.truncated && " (limit reached)"}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(0, steps.length - 1)}
                value={index}
                onChange={(e) => setIndex(Number(e.target.value))}
                className="mt-2 w-full accent-[var(--gw-accent)]"
                aria-label="Scrub through steps"
              />
              <p className="mt-1.5 min-h-5 text-[13px] text-text" aria-live="polite">
                {step ? describeStep(step, index, steps.length, returnObj) : "No steps were recorded."}
              </p>
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex items-center justify-between border-b border-border px-3 py-1.5 text-[12px] text-muted">
              <span className="font-medium uppercase tracking-wide">Names → Objects</span>
              <label className="flex cursor-pointer items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={primitivesAsObjects}
                  onChange={(e) => setPrimitivesAsObjects(e.target.checked)}
                  className="accent-[var(--gw-accent)]"
                />
                numbers &amp; strings as objects
              </label>
            </div>
            <div ref={stateRef} className="relative grid min-h-40 grid-cols-[auto_1fr] gap-x-14 overflow-x-auto p-3">
              <div className="space-y-2.5" aria-label="Frames">
                {step?.stack.map((frame, fi) => (
                  <div
                    key={`${fi}-${frame.name}`}
                    className={cn("min-w-32 rounded-lg border bg-surface", fi === step.stack.length - 1 ? "border-accent/60" : "border-border")}
                  >
                    <div className="border-b border-border px-2.5 py-1 text-[11.5px] font-semibold text-muted">
                      {frame.name === "Global frame" ? "Global names" : `${frame.name}()`}
                    </div>
                    {frame.vars.length === 0 && <div className="px-2.5 py-1.5 text-[12px] italic text-faint">no names yet</div>}
                    {frame.vars.map((v) => {
                      const obj = step.heap[String(v.ref)];
                      const inline = obj?.kind === "primitive" && !primitivesAsObjects;
                      const isFresh = fresh.has(`${fi}:${v.name}`);
                      return (
                        <div
                          key={v.name}
                          className={cn(
                            "flex items-center justify-between gap-3 px-2.5 py-1 font-mono text-[13px] transition-colors",
                            isFresh && "bg-accent-soft",
                          )}
                        >
                          <span className="font-semibold text-text">{v.name}</span>
                          {inline ? (
                            <span className="text-text">{obj?.repr}</span>
                          ) : (
                            <span ref={setAnchor(`var:${fi}:${v.name}`)} className="inline-flex items-center gap-1 text-[11px] text-faint">
                              <span className="sr-only">refers to object #{v.ref}</span>
                              <span aria-hidden className={cn("size-2 rounded-full", isFresh ? "bg-accent" : "bg-faint")} />
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
                {returnObj && step && step.stack.length > 1 && (
                  <div className="rounded-lg border border-violet/40 bg-violet-soft px-2.5 py-1.5 font-mono text-[12.5px]">
                    {step.event === "yield" ? "yielded value" : "return value"}: {returnObj.kind === "primitive" ? returnObj.repr : `#${step.returnRef}`}
                  </div>
                )}
              </div>
              <div className="space-y-2.5" aria-label="Objects">
                {objects.map(([key, obj]) => {
                  const isNew = !prevObjectKeys.has(key) && index > 0;
                  return (
                    <div
                      key={key}
                      ref={setAnchor(`obj:${key}`)}
                      className={cn("w-fit min-w-24 max-w-full rounded-lg border bg-surface-2 shadow-card", isNew ? "border-accent" : "border-border")}
                    >
                      <div className="flex items-center justify-between gap-3 border-b border-border px-2 py-0.5 text-[11px] text-muted">
                        <span className="font-mono">{obj.type}</span>
                        <span className="font-mono">#{key}</span>
                      </div>
                      <div className="px-2 py-1 font-mono text-[13px] text-text">
                        {obj.kind === "list" || obj.kind === "tuple" || obj.kind === "set" ? (
                          <div className="flex flex-wrap gap-1">
                            {obj.items?.length === 0 && <span className="text-faint">empty</span>}
                            {obj.items?.map((r, i) => (
                              <span key={i} className="inline-flex flex-col items-center rounded border border-border bg-surface px-1.5">
                                {obj.kind !== "set" && <span className="text-[9.5px] text-faint">{i}</span>}
                                {renderValue(r)}
                              </span>
                            ))}
                            {obj.size !== undefined && obj.items && obj.size > obj.items.length && <span className="text-faint">… {obj.size} total</span>}
                          </div>
                        ) : obj.kind === "dict" ? (
                          <div className="space-y-0.5">
                            {obj.entries?.length === 0 && <span className="text-faint">empty</span>}
                            {obj.entries?.map(([k, v], i) => (
                              <div key={i} className="flex gap-2">
                                {renderValue(k)}
                                <span className="text-faint">:</span>
                                {renderValue(v)}
                              </div>
                            ))}
                          </div>
                        ) : obj.kind === "instance" ? (
                          <div className="space-y-0.5">
                            {obj.attrs?.map(([name, v]) => (
                              <div key={name} className="flex gap-2">
                                <span className="text-muted">{name}</span>
                                <span className="text-faint">=</span>
                                {renderValue(v)}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className={cn(obj.kind === "function" && "text-violet")}>{obj.repr}</span>
                        )}
                      </div>
                      {isNew && (
                        <Badge tone="accent" className="m-1 mt-0">
                          new
                        </Badge>
                      )}
                    </div>
                  );
                })}
              </div>
              <svg className="pointer-events-none absolute left-0 top-0" width={box.w} height={box.h} aria-hidden>
                <defs>
                  <marker id="gw-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-faint)" />
                  </marker>
                  <marker id="gw-arrow-fresh" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M0,0 L8,4 L0,8 z" fill="var(--gw-accent)" />
                  </marker>
                </defs>
                {arrows.map((a) => (
                  <path
                    key={a.key}
                    d={a.d}
                    fill="none"
                    stroke={a.fresh ? "var(--gw-accent)" : "var(--gw-faint)"}
                    strokeWidth={a.fresh ? 2 : 1.4}
                    markerEnd={a.fresh ? "url(#gw-arrow-fresh)" : "url(#gw-arrow)"}
                  />
                ))}
              </svg>
            </div>
            <div className="border-t border-border">
              <div className="px-3 py-1.5 text-[12px] font-medium uppercase tracking-wide text-muted">Output so far</div>
              <pre className="min-h-8 whitespace-pre-wrap px-3 pb-2 font-mono text-[13px]">
                {stdoutSoFar || <span className="italic text-faint">(nothing printed yet)</span>}
              </pre>
            </div>
          </div>
        </div>
      )}
      {trace && trace.status !== "completed" && <RunOutput result={trace} />}
      {trace && trace.status === "completed" && trace.error && index === steps.length - 1 && <RunOutput result={trace} compact />}
    </div>
  );

  if (embedded) return body;
  return (
    <figure className="my-5 overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      {title && (
        <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-[13px] font-semibold text-text">
          <ScanSearch className="size-4 text-accent" aria-hidden /> {title}
        </div>
      )}
      {body}
    </figure>
  );
}
