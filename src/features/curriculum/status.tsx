import { Award, CircleDashed, CircleDot, Gauge } from "lucide-react";
import type { ConceptMastery, MasteryStatus } from "../../engine/mastery";
import { cn } from "../../components/ui";

export function StatusIcon({ status, className }: { status: MasteryStatus; className?: string }) {
  const c = cn("shrink-0", className);
  switch (status) {
    case "mastered":
      return <Award className={cn(c, "text-success")} aria-hidden />;
    case "proficient":
      return <Gauge className={cn(c, "text-info")} aria-hidden />;
    case "learning":
      return <CircleDot className={cn(c, "text-warning")} aria-hidden />;
    default:
      return <CircleDashed className={cn(c, "text-faint")} aria-hidden />;
  }
}

export function statusLabel(m: ConceptMastery): string {
  if (m.status === "mastered") {
    if (m.source === "diagnostic") return "Mastered (diagnostic)";
    if (m.source === "self-reported") return "Known (self-reported)";
    return "Mastered";
  }
  if (m.status === "proficient") return "Proficient";
  if (m.status === "learning") return m.hasLesson ? `Learning · ${Math.round(m.lessonProgress * 100)}% read` : "Learning";
  return m.hasLesson ? "Not started" : "Outline only";
}

export const statusColor: Record<MasteryStatus, string> = {
  mastered: "var(--gw-success)",
  proficient: "var(--gw-info)",
  learning: "var(--gw-warning)",
  "not-started": "var(--gw-faint)",
};
