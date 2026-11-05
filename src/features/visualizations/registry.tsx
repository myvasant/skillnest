import { lazy, Suspense, type ComponentType } from "react";
import { Shapes } from "lucide-react";
import { visualizationSchemas, isVisualizationId, type VisualizationId } from "../../content/visualizationSchemas";
import { Markdown } from "../../components/Markdown";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyProps = any;

const registry: Partial<Record<VisualizationId, ComponentType<AnyProps>>> = {
  "python-tracer": lazy(() => import("./PythonTracer").then((m) => ({ default: m.PythonTracer }))),
  "step-diagram": lazy(() => import("./StepDiagram").then((m) => ({ default: m.StepDiagram }))),
  "vector-similarity": lazy(() => import("./VectorSimilarity").then((m) => ({ default: m.VectorSimilarity }))),
  "complexity-growth": lazy(() => import("./ComplexityGrowth").then((m) => ({ default: m.ComplexityGrowth }))),
  "graph-traversal": lazy(() => import("./GraphTraversal").then((m) => ({ default: m.GraphTraversal }))),
  "gradient-descent": lazy(() => import("./GradientDescent").then((m) => ({ default: m.GradientDescent }))),
  "sql-join": lazy(() => import("./SqlJoin").then((m) => ({ default: m.SqlJoin }))),
  "neural-forward": lazy(() => import("./NeuralForward").then((m) => ({ default: m.NeuralForward }))),
  attention: lazy(() => import("./Attention").then((m) => ({ default: m.Attention }))),
};

export function VisualizationBlock({
  component,
  props,
  title,
  caption,
}: {
  component: string;
  props: Record<string, unknown>;
  title?: string;
  caption?: string;
}) {
  if (!isVisualizationId(component) || !registry[component]) {
    return <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted">Visualization “{component}” is not available.</p>;
  }
  const parsed = visualizationSchemas[component].safeParse(props);
  if (!parsed.success) return <p className="rounded-lg border border-danger/40 p-4 text-sm text-danger">Visualization “{component}” has invalid settings.</p>;
  const Component = registry[component]!;
  const wrapped = component !== "python-tracer";
  return (
    <figure className="not-prose my-6">
      <Suspense fallback={<div className="h-48 animate-pulse rounded-xl border border-border bg-surface-2" aria-label="Loading visualization" />}>
        {wrapped ? (
          <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
            {title && (
              <div className="flex items-center gap-2 border-b border-border px-4 py-2 text-[13px] font-semibold">
                <Shapes className="size-4 text-accent" aria-hidden />
                {title}
              </div>
            )}
            <Component {...(parsed.data as object)} />
          </div>
        ) : (
          <Component {...(parsed.data as object)} title={title} />
        )}
      </Suspense>
      {caption && (
        <figcaption className="mt-2 px-1 text-[13px] text-muted">
          <Markdown inline className="text-[13px] text-muted">
            {caption}
          </Markdown>
        </figcaption>
      )}
    </figure>
  );
}
