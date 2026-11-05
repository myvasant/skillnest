"""Analyse web-server access logs without loading them into memory.  (STARTER)

Parse Common Log Format (CLF) and Combined Log Format lines such as::

    203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html HTTP/1.1" 200 2326 "-" "curl/8.5.0"

into LogRecord objects, stream them through generators
(read_lines -> parse_records -> filter_records) and aggregate them in LogStats.

Work through the milestones in order; run one with ``python -m pytest -k Milestone1``.
Every function below has a docstring describing exactly what the tests expect.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# TODO (milestone 1): replace this placeholder with one compiled regex with named groups:
#   ip, ident, user, timestamp (inside [...]), method, path, protocol (inside "..."),
#   status (3 digits), size (digits or -), and an optional ' "referrer" "user agent"' part.
#   Keep it ReDoS-safe: use negated classes such as [^\]]+ and [^"]* instead of .* and
#   never nest quantifiers like (a+)+. Quotes inside the user agent are escaped as \".
LOG_LINE = re.compile(r"(?!)")  # (?!) never matches anything
TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"
MAX_MALFORMED_EXAMPLES = 20
EXCERPT_LENGTH = 80


class LogParseError(ValueError):
    """Raised when a line is not a valid access-log entry; ``reason`` explains why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class LogRecord:
    """One parsed request. ``timestamp`` is always timezone-aware."""

    ip: str
    timestamp: datetime
    method: str
    path: str
    protocol: str
    status: int
    size: int
    referrer: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class MalformedLine:
    """A line that could not be parsed, with its 1-based line number."""

    line_number: int
    reason: str
    text: str


@dataclass(frozen=True, slots=True)
class HourlyErrorRate:
    """Requests and errors in one hour (UTC)."""

    hour: datetime
    requests: int
    errors: int

    @property
    def rate(self) -> float:
        """Errors as a fraction of requests (0.0 when there were no requests)."""
        # TODO (milestone 3)
        raise NotImplementedError("HourlyErrorRate.rate")


# ---------------------------------------------------------------------------
# Milestone 1: parsing one line
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime:
    """Parse ``22/Oct/2026:13:05:01 +0000`` into an aware datetime.

    Use ``datetime.strptime(value, TIMESTAMP_FORMAT)``; turn its ValueError into
    ``LogParseError(f"invalid timestamp {value!r}")``.
    """
    # TODO (milestone 1)
    raise NotImplementedError("parse_timestamp")


def parse_line(line: str) -> LogRecord:
    """Parse one Common or Combined Log Format line.

    * strip a trailing "\\n" or "\\r\\n" and use ``LOG_LINE.fullmatch``;
    * no match -> LogParseError whose reason mentions "format";
    * bad timestamp -> LogParseError mentioning "timestamp" (use parse_timestamp);
    * status outside 100-599 -> LogParseError mentioning "status";
    * size "-" means 0; referrer or user agent "-" (or missing) means None.
    """
    # TODO (milestone 1)
    raise NotImplementedError("parse_line")


# ---------------------------------------------------------------------------
# Milestone 2: streaming pipeline
# ---------------------------------------------------------------------------


def read_lines(path: str | Path) -> Iterator[str]:
    """Yield the lines of a UTF-8 text file one at a time, without line endings.

    Must be a generator function (use ``yield``) so the file is only opened on the
    first ``next()``. Open it with ``encoding="utf-8-sig"`` (UTF-8 with or without the
    byte-order mark that Windows PowerShell 5.1 writes) and ``errors="replace"`` so bad
    bytes become U+FFFD.
    """
    # TODO (milestone 2)
    raise NotImplementedError("read_lines")


def parse_records(
    lines: Iterable[str],
    on_malformed: Callable[[MalformedLine], None] | None = None,
) -> Iterator[LogRecord]:
    """Lazily parse lines into records (a generator).

    Skip blank lines silently. Skip malformed lines too, but call ``on_malformed``
    (if given) with ``MalformedLine(line_number, reason, line)``; line numbers start
    at 1 and count blank lines. Never read further ahead than the next record needs.
    """
    # TODO (milestone 2): enumerate(lines, start=1), try parse_line, yield the record
    raise NotImplementedError("parse_records")


def filter_records(
    records: Iterable[LogRecord],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Iterator[LogRecord]:
    """Keep records with ``since <= timestamp < until`` (either bound may be None).

    Raise ValueError mentioning "timezone-aware" **immediately** (not on the first
    next()) if a bound is a naive datetime. Hint: validate first, then return a
    generator expression.
    """
    # TODO (milestone 2)
    raise NotImplementedError("filter_records")


# ---------------------------------------------------------------------------
# Milestone 3: statistics
# ---------------------------------------------------------------------------


def strip_query(path: str) -> str:
    """Return the path without its query string: ``/search?q=x`` -> ``/search``."""
    # TODO (milestone 3)
    raise NotImplementedError("strip_query")


def status_class(status: int) -> str:
    """Return the class of a status code: 404 -> ``"4xx"``."""
    # TODO (milestone 3)
    raise NotImplementedError("status_class")


def hour_bucket(timestamp: datetime) -> datetime:
    """Return the start of the UTC hour containing ``timestamp`` (convert to UTC first)."""
    # TODO (milestone 3)
    raise NotImplementedError("hour_bucket")


@dataclass
class _HourCounts:
    requests: int = 0
    errors: int = 0


@dataclass
class LogStats:
    """Running totals over a stream of records (add one record at a time)."""

    error_threshold: int = 500
    max_examples: int = MAX_MALFORMED_EXAMPLES
    # Running totals: not constructor arguments, every LogStats starts from zero.
    requests: int = field(default=0, init=False)
    bytes_sent: int = field(default=0, init=False)
    malformed: int = field(default=0, init=False)
    status_counts: Counter[int] = field(default_factory=Counter, init=False)
    path_counts: Counter[str] = field(default_factory=Counter, init=False)
    malformed_examples: list[MalformedLine] = field(default_factory=list, init=False)
    _hours: dict[datetime, _HourCounts] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        # TODO (milestone 3): raise ValueError mentioning "error_threshold" unless it is
        # between 100 and 599, and ValueError if max_examples is negative.
        pass

    def is_error(self, record: LogRecord) -> bool:
        """True if record.status >= error_threshold."""
        raise NotImplementedError("LogStats.is_error")

    def add(self, record: LogRecord) -> None:
        """Count one request: requests, bytes, status, path (query stripped), hour bucket."""
        raise NotImplementedError("LogStats.add")

    def add_malformed(self, item: MalformedLine) -> None:
        """Count a malformed line; keep only the first ``max_examples`` examples."""
        raise NotImplementedError("LogStats.add_malformed")

    @property
    def errors(self) -> int:
        """Total number of error responses."""
        raise NotImplementedError("LogStats.errors")

    @property
    def error_rate(self) -> float:
        """Errors as a fraction of all requests (0.0 when there are none)."""
        raise NotImplementedError("LogStats.error_rate")

    def status_classes(self) -> dict[str, int]:
        """Counts per status class as a dict ordered "1xx" .. "5xx"."""
        raise NotImplementedError("LogStats.status_classes")

    def top_paths(self, n: int) -> list[tuple[str, int]]:
        """The n most requested paths, most first, ties alphabetical; ValueError if n < 1.

        Note: Counter.most_common breaks ties by insertion order, so sort yourself.
        """
        raise NotImplementedError("LogStats.top_paths")

    def hourly_error_rates(self) -> list[HourlyErrorRate]:
        """One HourlyErrorRate per UTC hour that had requests, in time order."""
        raise NotImplementedError("LogStats.hourly_error_rates")


def analyze(
    lines: Iterable[str],
    *,
    error_threshold: int = 500,
    since: datetime | None = None,
    until: datetime | None = None,
    max_examples: int = MAX_MALFORMED_EXAMPLES,
) -> LogStats:
    """Run parse_records -> filter_records -> LogStats.add in a single pass."""
    # TODO (milestone 3): pass stats.add_malformed as the on_malformed callback
    raise NotImplementedError("analyze")


# ---------------------------------------------------------------------------
# Milestone 4: reports and command line
# ---------------------------------------------------------------------------


def safe_excerpt(text: str, limit: int = EXCERPT_LENGTH) -> str:
    """Make untrusted log text safe to print in a terminal.

    Replace each non-printable character with its escape (``ascii(ch)[1:-1]``, e.g.
    ``\\x1b``) and shorten text longer than ``limit`` to ``limit`` characters + "...".
    """
    # TODO (milestone 4)
    raise NotImplementedError("safe_excerpt")


def format_report(stats: LogStats, *, top: int = 5, show_malformed: bool = False) -> str:
    """Return the plain-text report (see the README for the exact lines)."""
    # TODO (milestone 4)
    raise NotImplementedError("format_report")


def report_to_dict(stats: LogStats, *, top: int = 5) -> dict[str, Any]:
    """Return the report as JSON-serialisable data (see the README for the keys)."""
    # TODO (milestone 4)
    raise NotImplementedError("report_to_dict")


def parse_cli_datetime(value: str) -> datetime:
    """argparse type: ISO 8601 date-time (datetime.fromisoformat); naive means UTC.

    Raise argparse.ArgumentTypeError for text that is not a date-time.
    """
    # TODO (milestone 4)
    raise NotImplementedError("parse_cli_datetime")


def positive_int(value: str) -> int:
    """argparse type: a whole number of at least 1 (else ArgumentTypeError)."""
    # TODO (milestone 4)
    raise NotImplementedError("positive_int")


def build_parser() -> argparse.ArgumentParser:
    """Create the parser: logfile (or -), --top, --error-threshold {400,500},
    --since, --until, --json and --show-malformed."""
    # TODO (milestone 4)
    raise NotImplementedError("build_parser")


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return the exit code.

    0 on success; 1 with ``error: cannot read ...`` on stderr if the file cannot be
    read; argparse exits with 2 for usage errors (also when --since >= --until:
    use ``parser.error``). ``-`` reads the log from sys.stdin.
    """
    # TODO (milestone 4)
    raise NotImplementedError("main")


if __name__ == "__main__":
    raise SystemExit(main())
