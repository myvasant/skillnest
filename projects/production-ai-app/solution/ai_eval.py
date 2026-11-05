"""ai_eval: measure a model on a small labelled set before you ship it.

Each case in ``data/eval_set.jsonl`` names the keywords a good output must contain.
The score of a case is its *keyword recall* (the fraction of expected keywords found);
the run passes when the mean recall reaches ``--threshold``.

Usage (from the kit folder)::

    python solution/ai_eval.py
    python solution/ai_eval.py --model ollama:llama3.2:1b --threshold 0.7

Keyword recall is a cheap, deterministic proxy. It cannot tell a fluent answer from
a keyword salad, so treat it as a regression alarm, not a quality verdict.
"""

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_service import Model, ModelError, ModelRequest, Task, model_from_name

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "eval_set.jsonl"
TASKS: tuple[Task, ...] = ("summarise", "answer")


@dataclass(frozen=True)
class EvalCase:
    """One labelled example."""

    id: str
    task: Task
    text: str
    expected_keywords: tuple[str, ...]
    question: str | None = None


@dataclass(frozen=True)
class CaseResult:
    """The score of one case; ``error`` names the exception if the model failed."""

    case_id: str
    recall: float
    missing: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class EvalReport:
    """All case results plus summary statistics."""

    results: tuple[CaseResult, ...]

    @property
    def mean_recall(self) -> float:
        """Average keyword recall over all cases (0.0 for an empty report)."""
        if not self.results:
            return 0.0
        return sum(r.recall for r in self.results) / len(self.results)

    @property
    def errors(self) -> int:
        """How many cases failed with a model error."""
        return sum(1 for r in self.results if r.error)


def _case_from_json(data: Any, where: str) -> EvalCase:
    """Validate one parsed JSON object and build an ``EvalCase``."""
    if not isinstance(data, dict):
        raise ValueError(f"{where}: each line must be a JSON object")
    case_id, task, text = data.get("id"), data.get("task"), data.get("text")
    keywords, question = data.get("expected_keywords"), data.get("question")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"{where}: 'id' must be a non-empty string")
    if task not in TASKS:
        raise ValueError(f"{where}: 'task' must be one of {list(TASKS)}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{where}: 'text' must be a non-empty string")
    if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k for k in keywords):
        raise ValueError(f"{where}: 'expected_keywords' must be a non-empty list of strings")
    if task == "answer" and (not isinstance(question, str) or not question.strip()):
        raise ValueError(f"{where}: answer cases need a 'question'")
    return EvalCase(case_id, task, text, tuple(keywords), question if task == "answer" else None)


def load_cases(path: Path) -> list[EvalCase]:
    """Read a JSON Lines file of cases; errors name the file and line number."""
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name} line {number}"
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{where}: invalid JSON ({error.msg})") from error
        case = _case_from_json(data, where)
        if case.id in seen:
            raise ValueError(f"{where}: duplicate case id {case.id!r}")
        seen.add(case.id)
        cases.append(case)
    return cases


def keyword_recall(output: str, keywords: Sequence[str]) -> tuple[float, tuple[str, ...]]:
    """Fraction of ``keywords`` found in ``output`` as whole words (case-insensitive).

    Returns ``(recall, missing_keywords)``. ``"1932"`` does not match ``"19321"``.
    """
    lowered = output.lower()
    missing = tuple(k for k in keywords if not re.search(rf"(?<!\w){re.escape(k.lower())}(?!\w)", lowered))
    return (len(keywords) - len(missing)) / len(keywords), missing


def evaluate(model: Model, cases: Sequence[EvalCase], *, timeout: float = 30.0) -> EvalReport:
    """Run every case through ``model``; a model error scores 0 for that case."""
    results: list[CaseResult] = []
    for case in cases:
        request = ModelRequest(case.task, case.text, case.question)
        try:
            output = model.complete(request, timeout=timeout)
        except ModelError as error:
            results.append(CaseResult(case.id, 0.0, case.expected_keywords, type(error).__name__))
            continue
        recall, missing = keyword_recall(output, case.expected_keywords)
        results.append(CaseResult(case.id, recall, missing))
    return EvalReport(tuple(results))


def format_report(report: EvalReport, threshold: float) -> str:
    """A small text table plus the PASS/FAIL verdict."""
    lines = [f"{'case':<22} {'recall':>6}  missing"]
    for r in report.results:
        detail = f"error: {r.error}" if r.error else (", ".join(r.missing) or "-")
        lines.append(f"{r.case_id:<22} {r.recall:>6.2f}  {detail}")
    verdict = "PASS" if report.mean_recall >= threshold else "FAIL"
    lines.append(f"mean keyword recall {report.mean_recall:.3f} (threshold {threshold:.2f}): {verdict}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point. Exit code 0 = pass, 1 = below threshold."""
    parser = argparse.ArgumentParser(description="Evaluate a model on a labelled set.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="JSON Lines file of cases")
    parser.add_argument("--model", default="fake", help="'fake' or 'ollama:<model>'")
    parser.add_argument("--threshold", type=float, default=0.8, help="minimum mean keyword recall")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds per model call")
    args = parser.parse_args(argv)
    report = evaluate(model_from_name(args.model), load_cases(args.data), timeout=args.timeout)
    print(format_report(report, args.threshold))
    return 0 if report.mean_recall >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
