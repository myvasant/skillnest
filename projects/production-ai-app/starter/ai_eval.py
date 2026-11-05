"""ai_eval: measure a model on a small labelled set before you ship it (milestone 6).

Each case in ``data/eval_set.jsonl`` names the keywords a good output must contain.
The score of a case is its *keyword recall* (the fraction of expected keywords found);
the run passes when the mean recall reaches ``--threshold``.

Usage (from the kit folder)::

    python starter/ai_eval.py
    python starter/ai_eval.py --model ollama:llama3.2:1b --threshold 0.7

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


def load_cases(path: Path) -> list[EvalCase]:
    """Read a JSON Lines file of cases; errors name the file and line number.

    Skip blank lines. Raise ``ValueError("<file> line N: ...")`` for invalid JSON, a
    missing/empty ``id``, a ``task`` other than summarise/answer, empty ``text``, an
    empty or non-string ``expected_keywords`` list, an answer case without a
    ``question``, or a duplicate ``id``. Summarise cases get ``question=None``.
    """
    # TODO(milestone 6)
    raise NotImplementedError("TODO(milestone 6): load_cases")


def keyword_recall(output: str, keywords: Sequence[str]) -> tuple[float, tuple[str, ...]]:
    """Fraction of ``keywords`` found in ``output`` as whole words (case-insensitive).

    Returns ``(recall, missing_keywords)`` with missing keywords as given. ``"1932"``
    must not match ``"19321"``: use ``re.escape`` with ``(?<!\\w)`` / ``(?!\\w)`` around it.
    """
    # TODO(milestone 6)
    raise NotImplementedError("TODO(milestone 6): keyword_recall")


def evaluate(model: Model, cases: Sequence[EvalCase], *, timeout: float = 30.0) -> EvalReport:
    """Run every case through ``model``; a ``ModelError`` scores 0 for that case.

    Record the error's class name in ``CaseResult.error`` and treat every keyword
    as missing.
    """
    # TODO(milestone 6)
    raise NotImplementedError("TODO(milestone 6): evaluate")


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
    """Command-line entry point. Exit code 0 = pass, 1 = below threshold.

    Options: ``--data`` (default DEFAULT_DATA), ``--model`` (default ``fake``),
    ``--threshold`` (default 0.8), ``--timeout`` (default 60 seconds per call).
    Print ``format_report(...)``.
    """
    # TODO(milestone 6): argparse, then evaluate(model_from_name(...), load_cases(...)).
    raise NotImplementedError("TODO(milestone 6): main")


if __name__ == "__main__":
    sys.exit(main())
