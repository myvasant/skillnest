import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from "lucide-react";
import { Button } from "../../components/ui";

/** Step state with optional autoplay (pauses at the end; respects reduced motion by using a slower pace). */
export function useStepper(total: number, intervalMs = 1400) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    if (index >= total - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setIndex((i) => Math.min(i + 1, total - 1)), intervalMs);
    return () => clearTimeout(t);
  }, [playing, index, total, intervalMs]);
  useEffect(() => {
    if (index > total - 1) setIndex(Math.max(0, total - 1));
  }, [total, index]);
  return {
    index,
    setIndex,
    playing,
    togglePlay: () => setPlaying((p) => !p),
    next: () => setIndex((i) => Math.min(i + 1, total - 1)),
    back: () => setIndex((i) => Math.max(i - 1, 0)),
    reset: () => {
      setPlaying(false);
      setIndex(0);
    },
  };
}

export function StepControls({ stepper, total, label }: { stepper: ReturnType<typeof useStepper>; total: number; label?: string }) {
  return (
    <div
      className="flex flex-wrap items-center gap-1"
      role="group"
      aria-label={label ?? "Step controls"}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") {
          e.preventDefault();
          stepper.next();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          stepper.back();
        }
      }}
    >
      <Button size="sm" variant="secondary" onClick={stepper.back} disabled={stepper.index === 0} icon={<ChevronLeft className="size-4" aria-hidden />}>
        Back
      </Button>
      <Button size="sm" variant="primary" onClick={stepper.next} disabled={stepper.index >= total - 1}>
        Next <ChevronRight className="size-4" aria-hidden />
      </Button>
      <Button size="sm" variant="ghost" onClick={stepper.togglePlay} aria-label={stepper.playing ? "Pause" : "Play automatically"} disabled={total < 2}>
        {stepper.playing ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
      </Button>
      <Button size="sm" variant="ghost" onClick={stepper.reset} aria-label="Reset" disabled={stepper.index === 0 && !stepper.playing}>
        <RotateCcw className="size-4" aria-hidden />
      </Button>
      <span className="ml-auto text-[12px] tabular-nums text-muted" aria-live="polite">
        Step {total ? stepper.index + 1 : 0} / {total}
      </span>
    </div>
  );
}

export const fmt = (n: number, digits = 3) => {
  if (!Number.isFinite(n)) return n > 0 ? "∞" : n < 0 ? "−∞" : "NaN";
  const r = Number(n.toFixed(digits));
  return Object.is(r, -0) ? "0" : String(r);
};
