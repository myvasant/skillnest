import { useState } from "react";
import { Play, RotateCcw } from "lucide-react";
import type { PredictItem as Predict } from "../../content/schema";
import { CodeView } from "../../components/CodeView";
import { Button } from "../../components/ui";
import { gradePrediction } from "../../engine/feedback";
import { python } from "../../python/client";
import type { RunResult } from "../../python/types";
import { RunOutput } from "../code/RunOutput";
import { ItemFrame, Verdict, type ItemProps } from "./shared";
import { reportAnswer } from "./record";

export function PredictItem({ item, gid, mode, onAnswered }: ItemProps<Predict>) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<{ correct: boolean; feedback: string | null } | null>(null);
  const [run, setRun] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const lines = Math.max(1, item.answer.replace(/\n$/, "").split("\n").length);

  const check = () => {
    const graded = gradePrediction(answer, item.answer, item.wrongAnswers);
    setResult(graded);
    reportAnswer(gid, mode, graded.correct, onAnswered);
  };

  const runIt = async () => {
    setRunning(true);
    setRun(await python.run(item.code));
    setRunning(false);
  };

  return (
    <ItemFrame item={item} gid={gid} status={result ? (result.correct ? "correct" : "incorrect") : null}>
      <div className="overflow-hidden rounded-lg border border-border">
        <CodeView code={item.code} />
      </div>
      <label className="mt-3 block text-[13px] font-medium text-muted" htmlFor={`${gid}-answer`}>
        Your predicted output{lines > 1 ? ` (${lines} lines)` : ""}
      </label>
      <textarea
        id={`${gid}-answer`}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        disabled={Boolean(result)}
        rows={Math.min(lines + 1, 8)}
        spellCheck={false}
        className="mt-1 w-full resize-y rounded-lg border border-border bg-code px-3 py-2 font-mono text-[14px] text-text focus:border-accent focus:outline-none"
        placeholder="Type exactly what the program prints"
      />
      {!result && (
        <Button className="mt-2" variant="primary" onClick={check} disabled={!answer.trim()}>
          Check prediction
        </Button>
      )}
      {result && (
        <Verdict
          correct={result.correct}
          feedback={result.feedback ?? (result.correct ? null : `The program prints:\n\n\`\`\`text\n${item.answer.replace(/\n$/, "")}\n\`\`\``)}
          explanation={item.explanation}
          extra={
            <div className="mt-3 flex flex-wrap gap-2">
              {mode === "practice" && (
                <Button size="sm" icon={<Play className="size-3.5" aria-hidden />} onClick={runIt} loading={running}>
                  Run it to confirm
                </Button>
              )}
              {mode === "practice" && !result.correct && (
                <Button
                  size="sm"
                  icon={<RotateCcw className="size-3.5" aria-hidden />}
                  onClick={() => {
                    setResult(null);
                    setRun(null);
                  }}
                >
                  Try again
                </Button>
              )}
            </div>
          }
        />
      )}
      {run && <RunOutput result={run} className="mt-3 rounded-lg border" />}
    </ItemFrame>
  );
}
