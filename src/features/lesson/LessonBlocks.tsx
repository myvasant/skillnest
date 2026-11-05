import type { ReactNode } from "react";
import { AlertTriangle, Briefcase, Compass, Info, Lightbulb, MessageCircleQuestion, Microscope, Sparkles, TriangleAlert } from "lucide-react";
import type { Block, Lesson } from "../../content/schema";
import { itemGid } from "../../content/build";
import { Markdown } from "../../components/Markdown";
import { cn } from "../../components/ui";
import { RunnableCode } from "../code/RunnableCode";
import { ItemView } from "../assessment/ItemView";
import { VisualizationBlock } from "../visualizations/registry";

const callouts: Record<string, { label: string; icon: ReactNode; className: string }> = {
  tip: { label: "Tip", icon: <Lightbulb className="size-4" aria-hidden />, className: "border-success/30 bg-success-soft/50 [&_.callout-title]:text-success" },
  note: { label: "Note", icon: <Info className="size-4" aria-hidden />, className: "border-info/30 bg-info-soft/50 [&_.callout-title]:text-info" },
  warning: {
    label: "Warning",
    icon: <TriangleAlert className="size-4" aria-hidden />,
    className: "border-warning/40 bg-warning-soft/60 [&_.callout-title]:text-warning",
  },
  misconception: {
    label: "Common misconception",
    icon: <AlertTriangle className="size-4" aria-hidden />,
    className: "border-danger/30 bg-danger-soft/50 [&_.callout-title]:text-danger",
  },
  analogy: {
    label: "Analogy",
    icon: <Compass className="size-4" aria-hidden />,
    className: "border-violet/30 bg-violet-soft/50 [&_.callout-title]:text-violet",
  },
  "deep-dive": {
    label: "Deep dive",
    icon: <Microscope className="size-4" aria-hidden />,
    className: "border-border-strong bg-surface-2 [&_.callout-title]:text-text",
  },
  production: {
    label: "In production",
    icon: <Briefcase className="size-4" aria-hidden />,
    className: "border-info/30 bg-info-soft/40 [&_.callout-title]:text-info",
  },
  interview: {
    label: "Interview angle",
    icon: <MessageCircleQuestion className="size-4" aria-hidden />,
    className: "border-accent/30 bg-accent-soft/50 [&_.callout-title]:text-accent",
  },
};

export function LessonBlock({ block, lesson, index, sectionId }: { block: Block; lesson: Lesson; index: number; sectionId: string }) {
  switch (block.type) {
    case "markdown":
      return <Markdown>{block.body}</Markdown>;
    case "code":
      return <RunnableCode block={block} storageKey={`example:${lesson.id}:${block.id ?? `${sectionId}-${index}`}`} />;
    case "callout": {
      const c = callouts[block.variant]!;
      return (
        <aside className={cn("not-prose my-5 rounded-xl border px-4 py-3", c.className)}>
          <p className="callout-title flex items-center gap-2 text-[13px] font-semibold">
            {c.icon}
            {block.title ?? c.label}
          </p>
          <Markdown className="mt-1.5 text-[15px]">{block.body}</Markdown>
        </aside>
      );
    }
    case "visualization":
      return <VisualizationBlock component={block.component} props={block.props} title={block.title} caption={block.caption} />;
    case "item": {
      const item = lesson.items.find((i) => i.id === block.ref);
      if (!item) return null;
      return <ItemView item={item} gid={itemGid(lesson.id, item.id)} mode="practice" />;
    }
  }
}

export function DeepBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-muted">
      <Sparkles className="size-3" aria-hidden /> Deep dive
    </span>
  );
}
