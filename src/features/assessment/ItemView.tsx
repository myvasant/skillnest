import type { Item } from "../../content/schema";
import { McqItem, TrueFalseItem } from "./ChoiceItems";
import { CodeExercise } from "./CodeExercise";
import { ExplainItem, ParsonsItem } from "./ExplainParsons";
import { PredictItem } from "./PredictItem";
import type { ItemMode } from "./shared";

export function ItemView({ item, gid, mode = "practice", onAnswered }: { item: Item; gid: string; mode?: ItemMode; onAnswered?: (correct: boolean) => void }) {
  switch (item.type) {
    case "mcq":
      return <McqItem item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
    case "true-false":
      return <TrueFalseItem item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
    case "predict-output":
      return <PredictItem item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
    case "code":
    case "debug":
      return <CodeExercise item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
    case "explain":
      return <ExplainItem item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
    case "parsons":
      return <ParsonsItem item={item} gid={gid} mode={mode} onAnswered={onAnswered} />;
  }
}
