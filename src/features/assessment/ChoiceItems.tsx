import { useId, useState } from "react";
import { RotateCcw } from "lucide-react";
import type { McqItem as Mcq, TrueFalseItem as TrueFalse } from "../../content/schema";
import { Markdown } from "../../components/Markdown";
import { Button, cn } from "../../components/ui";
import { ItemFrame, Verdict, seededShuffle, type ItemProps } from "./shared";
import { reportAnswer } from "./record";

export function McqItem({ item, gid, mode, onAnswered }: ItemProps<Mcq>) {
  const name = useId();
  const [options] = useState(() => seededShuffle(item.options, item.id));
  const [selected, setSelected] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const chosen = item.options.find((o) => o.id === submitted);
  const correct = chosen?.correct ?? false;

  const submit = () => {
    if (!selected) return;
    setSubmitted(selected);
    reportAnswer(gid, mode, item.options.find((o) => o.id === selected)?.correct ?? false, onAnswered);
  };

  return (
    <ItemFrame item={item} gid={gid} status={submitted ? (correct ? "correct" : "incorrect") : null}>
      <fieldset disabled={Boolean(submitted)}>
        <legend className="sr-only">Choose one answer</legend>
        <div className="space-y-2">
          {options.map((o) => {
            const isChosen = submitted === o.id;
            return (
              <label
                key={o.id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 text-[14.5px] transition-colors",
                  selected === o.id ? "border-accent bg-accent-soft/50" : "border-border hover:border-border-strong",
                  isChosen && (o.correct ? "border-success bg-success-soft/60" : "border-danger bg-danger-soft/60"),
                  submitted && !isChosen && "opacity-75",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  value={o.id}
                  checked={selected === o.id}
                  onChange={() => setSelected(o.id)}
                  className="mt-1 accent-[var(--gw-accent)]"
                />
                <Markdown inline className="text-[14.5px] leading-snug">
                  {o.text}
                </Markdown>
              </label>
            );
          })}
        </div>
      </fieldset>
      {!submitted && (
        <Button className="mt-3" variant="primary" onClick={submit} disabled={!selected}>
          Check answer
        </Button>
      )}
      {submitted && chosen && (
        <Verdict
          correct={correct}
          feedback={chosen.feedback}
          explanation={item.explanation}
          extra={
            mode === "practice" && !correct ? (
              <Button
                size="sm"
                className="mt-3"
                icon={<RotateCcw className="size-3.5" aria-hidden />}
                onClick={() => {
                  setSubmitted(null);
                  setSelected(null);
                }}
              >
                Try again
              </Button>
            ) : null
          }
        />
      )}
    </ItemFrame>
  );
}

export function TrueFalseItem({ item, gid, mode, onAnswered }: ItemProps<TrueFalse>) {
  const [answer, setAnswer] = useState<boolean | null>(null);
  const correct = answer === item.answer;
  const choose = (value: boolean) => {
    if (answer !== null) return;
    setAnswer(value);
    reportAnswer(gid, mode, value === item.answer, onAnswered);
  };
  return (
    <ItemFrame item={item} gid={gid} status={answer === null ? null : correct ? "correct" : "incorrect"}>
      <div className="flex gap-2" role="group" aria-label="Answer true or false">
        {[true, false].map((v) => (
          <Button
            key={String(v)}
            variant={answer === v ? (correct ? "primary" : "danger") : "secondary"}
            onClick={() => choose(v)}
            disabled={answer !== null}
            aria-pressed={answer === v}
          >
            {v ? "True" : "False"}
          </Button>
        ))}
      </div>
      {answer !== null && (
        <Verdict
          correct={correct}
          feedback={correct ? null : `The statement is ${item.answer ? "true" : "false"}.`}
          explanation={item.explanation}
          extra={
            mode === "practice" && !correct ? (
              <Button size="sm" className="mt-3" icon={<RotateCcw className="size-3.5" aria-hidden />} onClick={() => setAnswer(null)}>
                Try again
              </Button>
            ) : null
          }
        />
      )}
    </ItemFrame>
  );
}
