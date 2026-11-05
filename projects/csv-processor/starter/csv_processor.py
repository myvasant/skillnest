"""Clean a messy sales CSV export and summarise it per group, one row at a time.

Examples (once you have finished)::

    python csv_processor.py sales.csv
    python csv_processor.py sales.csv --group-by month --value quantity
    python csv_processor.py sales.csv --group-by product --summary-csv summary.csv

The pipeline is a chain of generators::

    file lines -> read_rows() -> clean_rows() -> build_report() -> format_report() / write_summary_csv()

Work through the milestones in order: replace every ``raise NotImplementedError`` and check your
progress with ``python -m pytest -k Milestone1`` (then 2, 3, 4, 5). The constants, the exception
classes and the dataclass fields are provided; keep their names, because the tests use them.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO, TypeVar

T = TypeVar("T")

REQUIRED_COLUMNS = ("order_id", "order_date", "region", "product", "quantity", "unit_price")
MISSING_MARKERS = frozenset({"", "na", "n/a", "nan", "null", "none", "-"})
DEFAULT_REGION = "Unknown"
GROUP_KEYS = ("region", "product", "month")
VALUE_FIELDS = ("revenue", "quantity")
EXTRA_KEY = "__extra__"
CURRENCY_SYMBOLS = "$£€"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CENTS = Decimal("0.01")

Row = dict[str, Any]
"""One raw row from ``csv.DictReader``: column name -> text (``None`` if the row was too short)."""


class CsvProcessingError(Exception):
    """The file as a whole cannot be processed (it is empty or required columns are missing)."""


class RowError(ValueError):
    """One row cannot be cleaned; ``column`` names the offending column."""

    def __init__(self, column: str, message: str) -> None:
        super().__init__(f"{column}: {message}")
        self.column = column
        self.message = message


# ---------------------------------------------------------------------------
# Milestone 1: parse and normalise single values
# ---------------------------------------------------------------------------


def is_missing(value: str | None) -> bool:
    """True for ``None`` and the "no value" markers in MISSING_MARKERS (compare stripped, lower-cased)."""
    raise NotImplementedError("is_missing")


def clean_text(value: str) -> str:
    """Strip the ends and collapse inner whitespace: ``"  Desk   lamp "`` -> ``"Desk lamp"``."""
    raise NotImplementedError("clean_text")


def parse_whole_number(text: str, *, minimum: int = 0) -> int:
    """Parse a whole number such as ``"3"`` or ``"3.0"`` and return an ``int``.

    TODO: raise ValueError("... is not a whole number") for "ten", "2.5", "" or "inf", and
    ValueError("must be at least <minimum> ...") below ``minimum``.
    Hint: ``Decimal(text)`` parses both "3" and "3.0"; compare it with ``to_integral_value()``.
    """
    raise NotImplementedError("parse_whole_number")


def parse_money(text: str) -> Decimal:
    """Parse a non-negative price with up to two decimals: ``"4.5"`` -> ``Decimal("4.50")``.

    TODO: allow one leading currency symbol from CURRENCY_SYMBOLS; reject (ValueError) text that
    is not a number, NaN/Infinity, negatives, more than two decimals and thousands separators
    such as "1,200.00" (``Decimal`` rejects the comma for you).
    """
    raise NotImplementedError("parse_money")


def parse_iso_date(text: str) -> date:
    """Parse a date written exactly ``YYYY-MM-DD``; raise ValueError for anything else."""
    raise NotImplementedError("parse_iso_date")


# ---------------------------------------------------------------------------
# Milestone 2: clean whole rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sale:
    """One cleaned, correctly typed row."""

    order_id: str
    order_date: date
    region: str
    product: str
    quantity: int
    unit_price: Decimal

    @property
    def revenue(self) -> Decimal:
        """``quantity * unit_price``."""
        raise NotImplementedError("Sale.revenue")

    @property
    def month(self) -> str:
        """The order month as ``YYYY-MM``."""
        raise NotImplementedError("Sale.month")


def clean_row(row: Row) -> Sale:
    """Turn one raw row into a :class:`Sale`.

    TODO:
      * If ``row.get(EXTRA_KEY)`` is non-empty the row had surplus fields: RowError("row", ...).
      * Clean text with clean_text; title-case the region; a missing region becomes DEFAULT_REGION.
      * Every other column is required: a missing value -> RowError(column, "value is missing").
      * Parse order_date, quantity (minimum 1) and unit_price with the Milestone 1 functions and turn
        their ValueError into RowError(column, str(error)) so the message keeps the bad value.
    """
    raise NotImplementedError("clean_row")


# ---------------------------------------------------------------------------
# Milestone 3: stream rows from a file
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rejected:
    """A row that could not be cleaned, with the line it came from."""

    line: int
    column: str
    reason: str

    def describe(self) -> str:
        """Human-readable form, e.g. ``line 6: quantity: 'ten' is not a whole number``."""
        raise NotImplementedError("Rejected.describe")


def read_rows(lines: Iterable[str]) -> Iterator[tuple[int, Row]]:
    """Yield ``(line_number, row)`` for each data row, reading one line at a time (a generator).

    TODO:
      * ``csv.DictReader(lines, restkey=EXTRA_KEY)``.
      * ``reader.fieldnames`` is None for an empty file -> CsvProcessingError("the file is empty ...").
      * Strip and lower-case the header names (you can assign ``reader.fieldnames``).
      * Missing required columns -> CsvProcessingError listing them, e.g. "quantity, unit_price".
      * ``reader.line_num`` is the line where the current row ends (the header is line 1).
    """
    raise NotImplementedError("read_rows")


def clean_rows(rows: Iterable[tuple[int, Row]]) -> Iterator[Sale | Rejected]:
    """Yield a Sale or a Rejected for every row, in order (a generator).

    TODO: catch RowError from clean_row. Remember the line where each order_id first appeared and
    reject repeats with the reason ``"duplicate of line <n>"``.
    """
    raise NotImplementedError("clean_rows")


# ---------------------------------------------------------------------------
# Milestone 4: group and aggregate
# ---------------------------------------------------------------------------


@dataclass
class GroupStats:
    """Running count / total / min / max for one group; ``add`` must not store the values."""

    count: int = 0
    total: Decimal = Decimal("0")
    minimum: Decimal | None = None
    maximum: Decimal | None = None

    def add(self, value: Decimal) -> None:
        """Include one more value."""
        raise NotImplementedError("GroupStats.add")

    @property
    def mean(self) -> Decimal:
        """Average rounded to cents with ROUND_HALF_UP; raise ValueError for an empty group."""
        raise NotImplementedError("GroupStats.mean")


def aggregate(sales: Iterable[Sale], *, by: str = "region", value: str = "revenue") -> dict[str, GroupStats]:
    """Group sales by ``region``, ``product`` or ``month`` and summarise ``revenue`` or ``quantity``.

    TODO: raise ValueError for a ``by`` not in GROUP_KEYS or a ``value`` not in VALUE_FIELDS.
    Return the groups sorted by name. Hint: ``getattr(sale, by)`` reads the attribute named ``by``.
    """
    raise NotImplementedError("aggregate")


@dataclass
class Report:
    """Everything learned in one pass over the file."""

    group_by: str
    value: str
    groups: dict[str, GroupStats] = field(default_factory=dict)
    rows_read: int = 0
    rejected_by_column: Counter[str] = field(default_factory=Counter)
    examples: list[Rejected] = field(default_factory=list)

    @property
    def rows_rejected(self) -> int:
        """How many rows were rejected, for any reason."""
        raise NotImplementedError("Report.rows_rejected")

    @property
    def rows_kept(self) -> int:
        """How many rows were cleaned successfully."""
        raise NotImplementedError("Report.rows_kept")


def build_report(
    rows: Iterable[tuple[int, Row]],
    *,
    group_by: str = "region",
    value: str = "revenue",
    max_examples: int = 10,
) -> Report:
    """Clean and aggregate ``rows`` in a single streaming pass (do not build a list of all rows).

    TODO: count every rejection per column, but keep only the first ``max_examples`` as examples.
    """
    raise NotImplementedError("build_report")


def summarise_file(
    path: Path, *, group_by: str = "region", value: str = "revenue", max_examples: int = 10
) -> Report:
    """Open ``path`` with ``newline=""`` and ``encoding="utf-8-sig"`` and build its report.

    ``utf-8-sig`` is UTF-8 that also skips the byte-order mark Excel writes at the start of a file.
    """
    raise NotImplementedError("summarise_file")


# ---------------------------------------------------------------------------
# Milestone 5: the report and the command-line interface
# ---------------------------------------------------------------------------


def escape_formula(text: str) -> str:
    """Prefix ``'`` to text that starts with one of FORMULA_PREFIXES so spreadsheets show it as text."""
    raise NotImplementedError("escape_formula")


def format_report(report: Report) -> str:
    """Render the report as plain text.

    Expected layout (the tests split lines on whitespace, so exact spacing is up to you)::

        Rows read: 10 | kept: 5 | rejected: 5
        Rejected rows by column:
          order_date   1
          ...
        Examples:
          line 6: quantity: 'ten' is not a whole number
          ...

        Revenue by region
        Region   Count   Total   Mean   Min   Max
        East         1   23.00  23.00  23.00  23.00
        ...
        TOTAL        5   69.50  13.90   9.00  23.00
    """
    raise NotImplementedError("format_report")


def write_summary_csv(report: Report, stream: TextIO) -> None:
    """Write ``<group_by>,count,total,mean,min,max`` and one row per group with ``csv.writer``.

    Pass every group name through escape_formula. No TOTAL row.
    """
    raise NotImplementedError("write_summary_csv")


def build_parser() -> argparse.ArgumentParser:
    """Create the parser.

    TODO: a positional ``input`` path (``type=Path``), ``--group-by`` (choices GROUP_KEYS, default
    region), ``--value`` (choices VALUE_FIELDS, default revenue), ``--summary-csv PATH`` and
    ``--max-examples N`` (a whole number >= 0, default 10).
    """
    raise NotImplementedError("build_parser")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; print the report and return 0, or print ``error: ...`` to stderr and return 1.

    TODO: a missing input file -> "error: <path> does not exist". CsvProcessingError, csv.Error,
    UnicodeDecodeError and other OSErrors -> "error: <path>: <message>".
    """
    raise NotImplementedError("main")


if __name__ == "__main__":
    raise SystemExit(main())
