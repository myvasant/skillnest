"""Clean a messy sales CSV export and summarise it per group, one row at a time.

Examples::

    python csv_processor.py sales.csv
    python csv_processor.py sales.csv --group-by month --value quantity
    python csv_processor.py sales.csv --group-by product --summary-csv summary.csv

The pipeline is a chain of generators::

    file lines -> read_rows() -> clean_rows() -> build_report() -> format_report() / write_summary_csv()

Rows are streamed: the file is never held in memory as a whole, so 10 rows and 10 million rows use
about the same memory. What does grow is one small ``GroupStats`` per group and the set of order ids
seen so far (needed to spot duplicates).
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
    """True for ``None`` and the usual "no value" markers: ``""``, ``"NA"``, ``"n/a"``, ``"null"`` ..."""
    return value is None or value.strip().lower() in MISSING_MARKERS


def clean_text(value: str) -> str:
    """Strip the ends and collapse inner whitespace: ``"  Desk   lamp "`` -> ``"Desk lamp"``."""
    return " ".join(value.split())


def parse_whole_number(text: str, *, minimum: int = 0) -> int:
    """Parse a whole number such as ``"3"`` or ``"3.0"`` (spreadsheets often add ``.0``).

    Raises:
        ValueError: for text that is not a whole number, or one below ``minimum``.
    """
    try:
        number = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"{text!r} is not a whole number") from None
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"{text!r} is not a whole number")
    if number < minimum:
        raise ValueError(f"must be at least {minimum}, got {text!r}")
    return int(number)


def parse_money(text: str) -> Decimal:
    """Parse a non-negative price with up to two decimals; one leading ``$``, ``£`` or ``€`` is allowed.

    ``"4.5"`` -> ``Decimal("4.50")``. Thousands separators (``"1,200.00"``) are rejected rather than
    guessed, because ``"1,200"`` means 1.2 in many countries.

    Raises:
        ValueError: if the text is not such a price.
    """
    cleaned = text.strip()
    if cleaned and cleaned[0] in CURRENCY_SYMBOLS:
        cleaned = cleaned[1:].strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"{text!r} is not a price like 4.99") from None
    if not amount.is_finite():
        raise ValueError(f"{text!r} is not a price like 4.99")
    if amount < 0:
        raise ValueError(f"must not be negative, got {text!r}")
    rounded = amount.quantize(CENTS)
    if rounded != amount:
        raise ValueError(f"{text!r} has more than two decimal places")
    return rounded


def parse_iso_date(text: str) -> date:
    """Parse a date written exactly ``YYYY-MM-DD``.

    Raises:
        ValueError: for other layouts (``01/03/2026``, ``20260301``) and impossible dates (``2026-02-30``).
    """
    cleaned = text.strip()
    if len(cleaned) != 10 or cleaned[4] != "-" or cleaned[7] != "-":
        raise ValueError(f"{text!r} is not a date written YYYY-MM-DD")
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f"{text!r} is not a real calendar date") from None


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
        """``quantity * unit_price`` (exact, because both are exact)."""
        return self.quantity * self.unit_price

    @property
    def month(self) -> str:
        """The order month as ``YYYY-MM``."""
        return f"{self.order_date:%Y-%m}"


def _required(row: Row, column: str) -> str:
    """Return the text in ``column`` or raise RowError if it is missing."""
    value = row.get(column)
    if is_missing(value):
        raise RowError(column, "value is missing")
    return str(value)


def _convert(row: Row, column: str, parse: Callable[[str], T]) -> T:
    """Parse a required column, turning the parser's ValueError into a RowError for that column."""
    text = _required(row, column)
    try:
        return parse(text)
    except ValueError as exc:
        raise RowError(column, str(exc)) from None


def clean_row(row: Row) -> Sale:
    """Turn one raw row into a :class:`Sale`.

    * Text is stripped and inner whitespace collapsed; regions are title-cased (``" south "`` -> ``"South"``).
    * A missing region becomes ``"Unknown"``; every other column is required.
    * ``quantity`` must be a whole number >= 1, ``unit_price`` a price >= 0, ``order_date`` ISO.

    Raises:
        RowError: naming the first column that is wrong (``"row"`` if the row has surplus fields).
    """
    extra = row.get(EXTRA_KEY)
    if extra:
        raise RowError("row", f"{len(extra)} more field(s) than the header (an unquoted comma?)")
    region = row.get("region")
    return Sale(
        order_id=clean_text(_required(row, "order_id")),
        order_date=_convert(row, "order_date", parse_iso_date),
        region=DEFAULT_REGION if is_missing(region) else clean_text(str(region)).title(),
        product=clean_text(_required(row, "product")),
        quantity=_convert(row, "quantity", lambda text: parse_whole_number(text, minimum=1)),
        unit_price=_convert(row, "unit_price", parse_money),
    )


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
        return f"line {self.line}: {self.column}: {self.reason}"


def read_rows(lines: Iterable[str]) -> Iterator[tuple[int, Row]]:
    """Yield ``(line_number, row)`` for each data row, reading one line at a time.

    Header names are stripped and lower-cased. ``line_number`` is the file line where the row ends
    (the header is line 1), so users can find it in an editor. Surplus fields are collected under
    ``EXTRA_KEY``; missing trailing fields are ``None``.

    Raises (when iteration starts, because this is a generator):
        CsvProcessingError: if there is no header or a required column is missing.
    """
    reader = csv.DictReader(lines, restkey=EXTRA_KEY)
    if reader.fieldnames is None:
        raise CsvProcessingError("the file is empty: expected a header row")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise CsvProcessingError(f"missing required column(s): {', '.join(missing)}")
    for row in reader:
        yield reader.line_num, row


def clean_rows(rows: Iterable[tuple[int, Row]]) -> Iterator[Sale | Rejected]:
    """Clean each row, yielding a :class:`Sale` or a :class:`Rejected` in the original order.

    A repeated ``order_id`` is rejected and points at the line where it first appeared.
    """
    first_seen: dict[str, int] = {}
    for line, row in rows:
        try:
            sale = clean_row(row)
        except RowError as exc:
            yield Rejected(line, exc.column, exc.message)
            continue
        if sale.order_id in first_seen:
            yield Rejected(line, "order_id", f"duplicate of line {first_seen[sale.order_id]}")
            continue
        first_seen[sale.order_id] = line
        yield sale


# ---------------------------------------------------------------------------
# Milestone 4: group and aggregate
# ---------------------------------------------------------------------------


@dataclass
class GroupStats:
    """Running count / total / min / max for one group; ``add`` is O(1) and keeps no rows."""

    count: int = 0
    total: Decimal = Decimal("0")
    minimum: Decimal | None = None
    maximum: Decimal | None = None

    def add(self, value: Decimal) -> None:
        """Include one more value."""
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    @property
    def mean(self) -> Decimal:
        """Average rounded to cents (half up).

        Raises:
            ValueError: for an empty group, which has no mean.
        """
        if not self.count:
            raise ValueError("an empty group has no mean")
        return (self.total / self.count).quantize(CENTS, rounding=ROUND_HALF_UP)


def _check_choice(value: str, allowed: Sequence[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}, not {value!r}")


def _add_sale(groups: dict[str, GroupStats], sale: Sale, by: str, value: str) -> None:
    key = str(getattr(sale, by))
    groups.setdefault(key, GroupStats()).add(Decimal(getattr(sale, value)))


def aggregate(sales: Iterable[Sale], *, by: str = "region", value: str = "revenue") -> dict[str, GroupStats]:
    """Group sales by ``region``, ``product`` or ``month`` and summarise ``revenue`` or ``quantity``.

    The result is sorted by group name (so months come out in calendar order).

    Raises:
        ValueError: for an unknown ``by`` or ``value``.
    """
    _check_choice(by, GROUP_KEYS, "by")
    _check_choice(value, VALUE_FIELDS, "value")
    groups: dict[str, GroupStats] = {}
    for sale in sales:
        _add_sale(groups, sale, by, value)
    return dict(sorted(groups.items()))


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
        return sum(self.rejected_by_column.values())

    @property
    def rows_kept(self) -> int:
        """How many rows were cleaned successfully."""
        return self.rows_read - self.rows_rejected


def build_report(
    rows: Iterable[tuple[int, Row]],
    *,
    group_by: str = "region",
    value: str = "revenue",
    max_examples: int = 10,
) -> Report:
    """Clean and aggregate ``rows`` in a single streaming pass.

    Every rejection is counted per column, but only the first ``max_examples`` are kept as examples,
    so memory stays bounded even for a file full of bad rows.
    """
    _check_choice(group_by, GROUP_KEYS, "group_by")
    _check_choice(value, VALUE_FIELDS, "value")
    report = Report(group_by=group_by, value=value)
    for item in clean_rows(rows):
        report.rows_read += 1
        if isinstance(item, Rejected):
            report.rejected_by_column[item.column] += 1
            if len(report.examples) < max_examples:
                report.examples.append(item)
        else:
            _add_sale(report.groups, item, group_by, value)
    report.groups = dict(sorted(report.groups.items()))
    return report


def summarise_file(
    path: Path, *, group_by: str = "region", value: str = "revenue", max_examples: int = 10
) -> Report:
    """Open ``path`` correctly for the csv module and build its report.

    ``newline=""`` lets the csv module handle line endings (including newlines inside quoted fields);
    ``utf-8-sig`` is UTF-8 that also skips the byte-order mark Excel puts at the start of a file.
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return build_report(read_rows(handle), group_by=group_by, value=value, max_examples=max_examples)


# ---------------------------------------------------------------------------
# Milestone 5: the report and the command-line interface
# ---------------------------------------------------------------------------


def escape_formula(text: str) -> str:
    """Neutralise spreadsheet formulas: text starting with ``= + - @`` (or tab/CR) gets a leading ``'``.

    Without this, a "region" such as ``=HYPERLINK("http://evil.example", "click")`` becomes a live
    formula when someone opens the summary in Excel or LibreOffice (CSV / formula injection).
    """
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def _grand_total(groups: dict[str, GroupStats]) -> GroupStats:
    overall = GroupStats()
    for stats in groups.values():
        overall.count += stats.count
        overall.total += stats.total
        for bound in (stats.minimum, stats.maximum):
            if bound is not None:
                overall.minimum = bound if overall.minimum is None else min(overall.minimum, bound)
                overall.maximum = bound if overall.maximum is None else max(overall.maximum, bound)
    return overall


def _stats_cells(stats: GroupStats) -> list[str]:
    return [str(stats.count), str(stats.total), str(stats.mean), str(stats.minimum), str(stats.maximum)]


def format_report(report: Report) -> str:
    """Render the report as plain text: row counts, rejection reasons, then the per-group table."""
    lines = [f"Rows read: {report.rows_read} | kept: {report.rows_kept} | rejected: {report.rows_rejected}"]
    if report.rows_rejected:
        lines.append("Rejected rows by column:")
        lines += [f"  {column:<12} {count}" for column, count in sorted(report.rejected_by_column.items())]
        lines.append("Examples:")
        lines += [f"  {item.describe()}" for item in report.examples]
    lines.append("")
    lines.append(f"{report.value.capitalize()} by {report.group_by}")
    if not report.groups:
        lines.append("No valid rows to summarise.")
        return "\n".join(lines)
    width = max(len(report.group_by), len("TOTAL"), *(len(name) for name in report.groups))
    header = [report.group_by.capitalize(), "Count", "Total", "Mean", "Min", "Max"]
    lines.append(f"{header[0]:<{width}}" + "".join(f"{cell:>12}" for cell in header[1:]))
    rows = [*report.groups.items(), ("TOTAL", _grand_total(report.groups))]
    for name, stats in rows:
        lines.append(f"{name:<{width}}" + "".join(f"{cell:>12}" for cell in _stats_cells(stats)))
    return "\n".join(lines)


def write_summary_csv(report: Report, stream: TextIO) -> None:
    """Write the per-group table as CSV (one row per group, no TOTAL row), escaping formulas.

    Open the target with ``newline=""`` and ``encoding="utf-8"``.
    """
    writer = csv.writer(stream)
    writer.writerow([report.group_by, "count", "total", "mean", "min", "max"])
    for name, stats in report.groups.items():
        writer.writerow([escape_formula(name), *_stats_cells(stats)])


def _non_negative_int(text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a whole number, got {text!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(prog="csv_processor", description="Clean a sales CSV and summarise it.")
    parser.add_argument("input", type=Path, help="CSV file to process")
    parser.add_argument("--group-by", choices=GROUP_KEYS, default="region", help="column to group by")
    parser.add_argument("--value", choices=VALUE_FIELDS, default="revenue", help="what to add up")
    parser.add_argument("--summary-csv", type=Path, help="also write the per-group table to this CSV file")
    parser.add_argument(
        "--max-examples", type=_non_negative_int, default=10, help="rejected rows to show (default: 10)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; return 0 on success and 1 if the file cannot be processed."""
    args = build_parser().parse_args(argv)
    try:
        report = summarise_file(
            args.input, group_by=args.group_by, value=args.value, max_examples=args.max_examples
        )
    except FileNotFoundError:
        print(f"error: {args.input} does not exist", file=sys.stderr)
        return 1
    except (CsvProcessingError, UnicodeDecodeError, csv.Error, OSError) as exc:
        print(f"error: {args.input}: {exc}", file=sys.stderr)
        return 1
    print(format_report(report))
    if args.summary_csv is not None:
        with args.summary_csv.open("w", newline="", encoding="utf-8") as handle:
            write_summary_csv(report, handle)
        print(f"\nSummary written to {args.summary_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
