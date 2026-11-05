"""Expense tracker: record expenses from the command line and keep them in a JSON file.

Examples::

    python expense_tracker.py add 12.50 groceries --date 2026-10-01 --description "weekly shop"
    python expense_tracker.py list --month 2026-10
    python expense_tracker.py summary --by month
    python expense_tracker.py --file work.json summary --by category

Money is held as :class:`decimal.Decimal`, never ``float``. Binary floating point cannot represent
most decimal fractions exactly (``0.1 + 0.2 == 0.30000000000000004``), so float totals drift by
fractions of a cent. ``Decimal("0.10") + Decimal("0.20") == Decimal("0.30")`` exactly.
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
        """The calendar month of the expense as ``YYYY-MM``."""
        return f"{self.spent_on:%Y-%m}"

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-friendly dict. The amount is a string so no precision is lost."""
        return {
            "amount": str(self.amount),
            "category": self.category,
            "date": self.spent_on.isoformat(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Expense:
        """Rebuild an expense from :meth:`to_dict` output, validating it again.

        Raises:
            ExpenseError: if ``data`` is not a dict, lacks a field, or holds an invalid value.
        """
        if not isinstance(data, dict):
            raise ExpenseError("each expense must be a JSON object")
        missing = [key for key in ("amount", "category", "date") if key not in data]
        if missing:
            raise ExpenseError(f"missing field(s): {', '.join(missing)}")
        return make_expense(
            str(data["amount"]), str(data["category"]), str(data["date"]), str(data.get("description", ""))
        )


def parse_amount(text: str | Decimal) -> Decimal:
    """Parse a positive amount with at most two decimal places: ``"12.5"`` -> ``Decimal("12.50")``.

    Raises:
        ExpenseError: for text that is not a number, is zero or negative, too large, or has
            more than two decimal places.
    """
    try:
        amount = Decimal(str(text).strip())
    except InvalidOperation:
        raise ExpenseError(f"amount must be a number like 12.50, not {text!r}") from None
    if not amount.is_finite():
        raise ExpenseError(f"amount must be a number like 12.50, not {text!r}")
    if amount <= 0:
        raise ExpenseError(f"amount must be greater than zero, not {text!r}")
    if amount > MAX_AMOUNT:
        raise ExpenseError(f"amount {text!r} is larger than the limit of {MAX_AMOUNT}")
    rounded = amount.quantize(CENTS)
    if rounded != amount:
        raise ExpenseError(f"amount can have at most two decimal places, not {text!r}")
    return rounded


def parse_date(text: str | date) -> date:
    """Parse an ISO date written exactly as ``YYYY-MM-DD``.

    Raises:
        ExpenseError: for any other format or an impossible date such as 2026-02-30.
    """
    if isinstance(text, date):
        return text
    cleaned = text.strip()
    error = ExpenseError(f"date must be a real date written YYYY-MM-DD (e.g. 2026-10-01), not {text!r}")
    # date.fromisoformat also accepts forms like "20261001"; insist on the readable one.
    if len(cleaned) != 10 or cleaned[4] != "-" or cleaned[7] != "-":
        raise error
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise error from None


def parse_month(text: str) -> str:
    """Validate a month written ``YYYY-MM`` and return it unchanged (without spaces).

    Raises:
        ExpenseError: for any other format or a month outside 01-12.
    """
    cleaned = text.strip()
    year, sep, month = cleaned.partition("-")
    if not (sep and len(year) == 4 and len(month) == 2 and year.isdigit() and month.isdigit()):
        raise ExpenseError(f"month must be written YYYY-MM (e.g. 2026-10), not {text!r}")
    if not 1 <= int(month) <= 12:
        raise ExpenseError(f"month must be between 01 and 12, not {text!r}")
    return cleaned


def normalise_category(text: str) -> str:
    """Lower-case a category and collapse its spaces: ``"  Eating   Out "`` -> ``"eating out"``.

    Raises:
        ExpenseError: if the category is empty or longer than ``MAX_CATEGORY_LENGTH``.
    """
    category = " ".join(text.split()).lower()
    if not category:
        raise ExpenseError("category must not be empty")
    if len(category) > MAX_CATEGORY_LENGTH:
        raise ExpenseError(f"category must be at most {MAX_CATEGORY_LENGTH} characters long")
    return category


def clean_description(text: str) -> str:
    """Collapse whitespace (including newlines) in a description and limit its length.

    Raises:
        ExpenseError: if the description is longer than ``MAX_DESCRIPTION_LENGTH``.
    """
    description = " ".join(text.split())
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ExpenseError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters long")
    return description


def make_expense(
    amount: str | Decimal, category: str, spent_on: str | date, description: str = ""
) -> Expense:
    """Validate raw values and build an :class:`Expense`.

    Raises:
        ExpenseError: if any value is invalid (the message says which one and why).
    """
    return Expense(
        amount=parse_amount(amount),
        category=normalise_category(category),
        spent_on=parse_date(spent_on),
        description=clean_description(description),
    )


# ---------------------------------------------------------------------------
# Milestone 2: safe JSON storage
# ---------------------------------------------------------------------------


def load_expenses(path: Path) -> list[Expense]:
    """Load every expense stored in ``path``. A file that does not exist yet means "no expenses".

    Raises:
        ExpenseError: if the file is not valid JSON, has the wrong shape, or holds an invalid expense.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except UnicodeDecodeError as exc:
        raise ExpenseError(f"{path} is not a UTF-8 text file: {exc.reason}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExpenseError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg}). "
            "Fix the file, or move it aside to start a new one."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("expenses"), list):
        raise ExpenseError(f'{path} is not an expense file: expected an object with an "expenses" list')
    if data.get("version") != FILE_FORMAT_VERSION:
        raise ExpenseError(f"{path} has unsupported format version {data.get('version')!r}")
    expenses = []
    for number, record in enumerate(data["expenses"], start=1):
        try:
            expenses.append(Expense.from_dict(record))
        except ExpenseError as exc:
            raise ExpenseError(f"{path}: expense #{number} is invalid: {exc}") from exc
    return expenses


def save_expenses(path: Path, expenses: Iterable[Expense]) -> None:
    """Write all expenses to ``path`` atomically.

    The JSON goes to a temporary file in the *same directory* first; ``os.replace`` then swaps it
    in as one step. A crash, a full disk or an exception part-way through leaves the previous file
    untouched instead of half-written, and the temporary file is removed.
    """
    payload = {"version": FILE_FORMAT_VERSION, "expenses": [expense.to_dict() for expense in expenses]}
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def add_expense(path: Path, expense: Expense) -> int:
    """Append ``expense`` to the file at ``path`` and return how many expenses it now holds.

    The existing file is loaded (and validated) first, so a corrupt file is reported, never overwritten.
    """
    expenses = load_expenses(path)
    expenses.append(expense)
    save_expenses(path, expenses)
    return len(expenses)


# ---------------------------------------------------------------------------
# Milestone 3: filters, totals and summaries
# ---------------------------------------------------------------------------


def filter_expenses(
    expenses: Iterable[Expense], *, category: str | None = None, month: str | None = None
) -> list[Expense]:
    """Return the expenses matching ``category`` and/or ``month`` (``YYYY-MM``), oldest first.

    Expenses on the same date keep the order they were added in (``sorted`` is stable).
    """
    wanted_category = normalise_category(category) if category is not None else None
    wanted_month = parse_month(month) if month is not None else None
    selected = [
        expense
        for expense in expenses
        if (wanted_category is None or expense.category == wanted_category)
        and (wanted_month is None or expense.month == wanted_month)
    ]
    return sorted(selected, key=lambda expense: expense.spent_on)


def total(expenses: Iterable[Expense]) -> Decimal:
    """Add up the amounts. The start value ``0.00`` keeps two decimal places for an empty list."""
    return sum((expense.amount for expense in expenses), ZERO)


def summarise_by_category(expenses: Iterable[Expense]) -> dict[str, Decimal]:
    """Total per category, largest total first (ties in alphabetical order)."""
    totals: dict[str, Decimal] = {}
    for expense in expenses:
        totals[expense.category] = totals.get(expense.category, ZERO) + expense.amount
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


def summarise_by_month(expenses: Iterable[Expense]) -> dict[str, Decimal]:
    """Total per ``YYYY-MM`` month, in calendar order."""
    totals: dict[str, Decimal] = {}
    for expense in expenses:
        totals[expense.month] = totals.get(expense.month, ZERO) + expense.amount
    return dict(sorted(totals.items()))


def format_expenses(expenses: Sequence[Expense]) -> str:
    """Render expenses as an aligned table with a closing count-and-total line."""
    if not expenses:
        return "No expenses found."
    lines = [f"{'Date':<10}  {'Category':<15}  {'Amount':>10}  Description"]
    for expense in expenses:
        when = expense.spent_on.isoformat()
        row = f"{when:<10}  {expense.category:<15}  {expense.amount:>10}  {expense.description}"
        lines.append(row.rstrip())
    lines.append(f"{len(expenses)} expense(s), total {total(expenses)}")
    return "\n".join(lines)


def format_summary(totals: dict[str, Decimal], label: str) -> str:
    """Render a ``{group: total}`` mapping as a two-column table ending with a TOTAL row."""
    if not totals:
        return "No expenses found."
    width = max(len(label), len("TOTAL"), *(len(name) for name in totals))
    lines = [f"{label:<{width}}  {'Total':>10}"]
    lines += [f"{name:<{width}}  {amount:>10}" for name, amount in totals.items()]
    lines.append(f"{'TOTAL':<{width}}  {sum(totals.values(), ZERO):>10}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Milestone 4: the command-line interface
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with the ``add``, ``list`` and ``summary`` subcommands."""
    parser = argparse.ArgumentParser(prog="expense_tracker", description="Track expenses in a JSON file.")
    parser.add_argument(
        "--file", type=Path, default=Path(DEFAULT_FILE), help=f"data file to use (default: {DEFAULT_FILE})"
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add = commands.add_parser("add", help="record an expense")
    add.add_argument("amount", help="positive amount with up to two decimals, e.g. 12.50")
    add.add_argument("category", help="for example groceries or transport")
    add.add_argument("--date", dest="spent_on", help="YYYY-MM-DD (default: today)")
    add.add_argument("--description", "-d", default="", help="optional note")

    show = commands.add_parser("list", help="show expenses, oldest first")
    show.add_argument("--category", help="only this category")
    show.add_argument("--month", help="only this month, YYYY-MM")

    summary = commands.add_parser("summary", help="totals per category or per month")
    summary.add_argument("--by", choices=("category", "month"), default="category", help="how to group")
    summary.add_argument("--month", help="only include this month, YYYY-MM")
    return parser


def _run_add(args: argparse.Namespace, today: date) -> str:
    expense = make_expense(args.amount, args.category, args.spent_on or today, args.description)
    count = add_expense(args.file, expense)
    return (
        f"Added {expense.amount} to {expense.category} on {expense.spent_on.isoformat()} ({count} in total)."
    )


def _run_list(args: argparse.Namespace) -> str:
    expenses = filter_expenses(load_expenses(args.file), category=args.category, month=args.month)
    return format_expenses(expenses)


def _run_summary(args: argparse.Namespace) -> str:
    expenses = filter_expenses(load_expenses(args.file), month=args.month)
    if args.by == "month":
        return format_summary(summarise_by_month(expenses), "Month")
    return format_summary(summarise_by_category(expenses), "Category")


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    """Run the CLI and return an exit code (0 = success, 1 = error, 2 = bad usage via argparse).

    ``today`` is the default date for ``add``; tests pass it so they never depend on the clock.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "add":
            output = _run_add(args, today or date.today())
        elif args.command == "list":
            output = _run_list(args)
        else:
            output = _run_summary(args)
    except (ExpenseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
