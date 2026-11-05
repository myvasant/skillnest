"""Expense tracker: record expenses from the command line and keep them in a JSON file.

Examples (once you have finished)::

    python expense_tracker.py add 12.50 groceries --date 2026-10-01 --description "weekly shop"
    python expense_tracker.py list --month 2026-10
    python expense_tracker.py summary --by month
    python expense_tracker.py --file work.json summary --by category

Money is held as :class:`decimal.Decimal`, never ``float``. Binary floating point cannot represent
most decimal fractions exactly (``0.1 + 0.2 == 0.30000000000000004``), so float totals drift by
fractions of a cent. ``Decimal("0.10") + Decimal("0.20") == Decimal("0.30")`` exactly.

Work through the milestones in order. Each function says what it must do; replace every
``raise NotImplementedError`` with your implementation and run ``python -m pytest -k Milestone1``
(then 2, 3, 4) to check your progress.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

DEFAULT_FILE = "expenses.json"
FILE_FORMAT_VERSION = 1
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("1000000")
MAX_CATEGORY_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 200


class ExpenseError(Exception):
    """A problem the user can fix: invalid input or an unreadable data file."""


# ---------------------------------------------------------------------------
# Milestone 1: the model and its validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expense:
    """One expense. Build instances with :func:`make_expense` so every value is validated."""

    amount: Decimal
    category: str
    spent_on: date
    description: str = ""

    @property
    def month(self) -> str:
        """The calendar month of the expense as ``YYYY-MM`` (hint: an f-string with ``:%Y-%m``)."""
        raise NotImplementedError("Expense.month")

    def to_dict(self) -> dict[str, str]:
        """Return ``{"amount": "12.50", "category": ..., "date": "2026-10-01", "description": ...}``.

        TODO: store the amount as a *string* so JSON never turns it into a float.
        """
        raise NotImplementedError("Expense.to_dict")

    @classmethod
    def from_dict(cls, data: Any) -> Expense:
        """Rebuild an expense from :meth:`to_dict` output, validating it again with make_expense.

        TODO: raise ExpenseError if ``data`` is not a dict or lacks amount/category/date.
        ``description`` is optional (default "").
        """
        raise NotImplementedError("Expense.from_dict")


def parse_amount(text: str | Decimal) -> Decimal:
    """Parse a positive amount with at most two decimal places: ``"12.5"`` -> ``Decimal("12.50")``.

    TODO:
      * ``Decimal(str(text).strip())``; turn ``InvalidOperation`` into ExpenseError.
      * Reject NaN/Infinity (``is_finite()``), zero and negatives, and anything above MAX_AMOUNT.
      * ``amount.quantize(CENTS)`` gives two decimal places; if that changes the value, the input
        had too many decimals ("1.234") - reject it.
    """
    raise NotImplementedError("parse_amount")


def parse_date(text: str | date) -> date:
    """Parse an ISO date written exactly as ``YYYY-MM-DD``; a ``date`` passes through unchanged.

    TODO: insist on the 10-character form with dashes at positions 4 and 7 (``date.fromisoformat``
    alone also accepts "20261001"), then use ``date.fromisoformat``. Raise ExpenseError with a
    message that contains "YYYY-MM-DD" for anything else, including impossible dates like 2026-02-30.
    """
    raise NotImplementedError("parse_date")


def parse_month(text: str) -> str:
    """Validate a month written ``YYYY-MM`` (month 01-12) and return it without surrounding spaces.

    TODO: raise ExpenseError for "2026-1", "2026-13", "Oct 2026", "2026-10-01" ...
    """
    raise NotImplementedError("parse_month")


def normalise_category(text: str) -> str:
    """Lower-case a category and collapse its spaces: ``"  Eating   Out "`` -> ``"eating out"``.

    TODO: raise ExpenseError if the result is empty or longer than MAX_CATEGORY_LENGTH.
    Hint: ``" ".join(text.split())`` collapses runs of whitespace.
    """
    raise NotImplementedError("normalise_category")


def clean_description(text: str) -> str:
    """Collapse whitespace (including newlines) in a description; reject more than 200 characters."""
    raise NotImplementedError("clean_description")


def make_expense(
    amount: str | Decimal, category: str, spent_on: str | date, description: str = ""
) -> Expense:
    """Validate raw values with the functions above and build an :class:`Expense`."""
    raise NotImplementedError("make_expense")


# ---------------------------------------------------------------------------
# Milestone 2: safe JSON storage
# ---------------------------------------------------------------------------


def load_expenses(path: Path) -> list[Expense]:
    """Load every expense stored in ``path``. A file that does not exist yet means "no expenses".

    File format: ``{"version": 1, "expenses": [ {...}, {...} ]}``

    TODO:
      * read with ``encoding="utf-8"``; FileNotFoundError -> return [].
      * ``json.JSONDecodeError`` -> ExpenseError whose message names the file and says "not valid JSON".
      * wrong shape (not an object, no "expenses" list, wrong version) -> ExpenseError.
      * an invalid record -> ExpenseError saying which one, e.g. "expense #2 is invalid: ...".
    """
    raise NotImplementedError("load_expenses")


def save_expenses(path: Path, expenses: Iterable[Expense]) -> None:
    """Write all expenses to ``path`` atomically.

    TODO:
      1. Build the JSON text first (``json.dumps(..., indent=2)``).
      2. Create the parent folder if needed.
      3. ``tempfile.mkstemp(dir=path.parent)`` -> write the text to that temporary file
         (``os.fdopen(fd, "w", encoding="utf-8")``), flush and ``os.fsync`` it.
      4. ``os.replace(temp, path)`` swaps it in as one step.
      5. If anything fails, delete the temporary file and re-raise the exception.
    """
    raise NotImplementedError("save_expenses")


def add_expense(path: Path, expense: Expense) -> int:
    """Append ``expense`` to the file at ``path``; return how many expenses it now holds.

    Load first, so a corrupt file is reported (ExpenseError) and never overwritten.
    """
    raise NotImplementedError("add_expense")


# ---------------------------------------------------------------------------
# Milestone 3: filters, totals and summaries
# ---------------------------------------------------------------------------


def filter_expenses(
    expenses: Iterable[Expense], *, category: str | None = None, month: str | None = None
) -> list[Expense]:
    """Return the expenses matching ``category`` and/or ``month`` (``YYYY-MM``), oldest first.

    TODO: normalise the category query and validate the month with the Milestone 1 functions.
    Expenses on the same date keep the order they were added in (``sorted`` is stable).
    """
    raise NotImplementedError("filter_expenses")


def total(expenses: Iterable[Expense]) -> Decimal:
    """Add up the amounts; an empty list totals ``Decimal("0.00")`` (hint: ``sum(..., ZERO)``)."""
    raise NotImplementedError("total")


def summarise_by_category(expenses: Iterable[Expense]) -> dict[str, Decimal]:
    """Total per category, largest total first; ties in alphabetical order."""
    raise NotImplementedError("summarise_by_category")


def summarise_by_month(expenses: Iterable[Expense]) -> dict[str, Decimal]:
    """Total per ``YYYY-MM`` month, in calendar order."""
    raise NotImplementedError("summarise_by_month")


def format_expenses(expenses: Sequence[Expense]) -> str:
    """Render an aligned table: a header line with Date/Category/Amount/Description, one line per
    expense starting with its ISO date, and a last line like ``4 expense(s), total 60.70``.

    Return ``"No expenses found."`` for an empty list.
    """
    raise NotImplementedError("format_expenses")


def format_summary(totals: dict[str, Decimal], label: str) -> str:
    """Render ``{group: total}`` as two columns: a ``<label>  Total`` header, one line per group and
    a final ``TOTAL`` line. Return ``"No expenses found."`` when ``totals`` is empty.
    """
    raise NotImplementedError("format_summary")


# ---------------------------------------------------------------------------
# Milestone 4: the command-line interface
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Create the parser.

    TODO:
      * a global ``--file`` option (``type=Path``, default ``DEFAULT_FILE``);
      * ``add AMOUNT CATEGORY [--date YYYY-MM-DD] [--description/-d TEXT]``;
      * ``list [--category C] [--month YYYY-MM]``;
      * ``summary [--by category|month] [--month YYYY-MM]``.
      Use ``parser.add_subparsers(dest="command", required=True)``.
    """
    raise NotImplementedError("build_parser")


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    """Run the CLI and return an exit code (0 = success, 1 = error; argparse exits with 2 itself).

    TODO: parse ``argv``, run the chosen command, print its output. Catch ExpenseError and OSError,
    print ``error: <message>`` to ``sys.stderr`` and return 1. ``today`` is the default date for
    ``add`` (use ``date.today()`` only when it is None) so tests never depend on the clock.
    Example output of add: ``Added 12.50 to groceries on 2026-10-01 (1 in total).``
    """
    raise NotImplementedError("main")


if __name__ == "__main__":
    raise SystemExit(main())
