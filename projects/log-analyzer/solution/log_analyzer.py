"""Analyse web-server access logs without loading them into memory.

The module parses Common Log Format (CLF) and Combined Log Format lines such as::

    203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html HTTP/1.1" 200 2326 "-" "curl/8.5.0"

into :class:`LogRecord` objects, streams them through generator functions
(:func:`read_lines` -> :func:`parse_records` -> :func:`filter_records`) and
aggregates them in a :class:`LogStats` accumulator: status codes, status classes,
top paths and the error rate per hour.

Command line::

    python log_analyzer.py access.log --top 5
    python log_analyzer.py access.log --json --error-threshold 400
    Get-Content access.log | python log_analyzer.py -        (PowerShell)
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

# One compiled pattern with named groups. Every repeated part is a negated character
# class followed by a fixed delimiter, so matching time grows linearly with the line
# length (no nested quantifiers that could backtrack catastrophically: ReDoS).
LOG_LINE = re.compile(
    r"(?P<ip>[0-9A-Fa-f.:]+) "  # IPv4 or IPv6 address of the client
    r"(?P<ident>\S+) (?P<user>\S+) "  # identd and user name, usually "-"
    r"\[(?P<timestamp>[^\]]+)\] "  # [22/Oct/2026:13:05:01 +0000]
    r'"(?P<method>[A-Z]+) (?P<path>[^\s"]+) (?P<protocol>HTTP/\d(?:\.\d)?)" '
    r"(?P<status>\d{3}) (?P<size>\d+|-)"
    # Combined Log Format adds referrer and user agent; quotes inside them are escaped as \".
    r'(?: "(?P<referrer>(?:[^"\\]|\\.)*)" "(?P<user_agent>(?:[^"\\]|\\.)*)")?'
)
# %b (month abbreviation) follows the LC_TIME locale; Python keeps the "C" locale
# (English names) unless a program calls locale.setlocale, so "Oct" always parses.
TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"
MAX_MALFORMED_EXAMPLES = 20
EXCERPT_LENGTH = 80


class LogParseError(ValueError):
    """Raised when a line is not a valid access-log entry.

    ``reason`` is a short, human-readable explanation such as
    ``"invalid status code 999"``.
    """

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
        return self.errors / self.requests if self.requests else 0.0


# ---------------------------------------------------------------------------
# Milestone 1: parsing one line
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime:
    """Parse ``22/Oct/2026:13:05:01 +0000`` into an aware datetime."""
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError:
        raise LogParseError(f"invalid timestamp {value!r}") from None


def _optional(value: str | None) -> str | None:
    """Return None for a missing or "-" field, otherwise the value itself."""
    return None if value in (None, "-") else value


def parse_line(line: str) -> LogRecord:
    """Parse one Common or Combined Log Format line.

    Raises:
        LogParseError: if the line does not match the format, the timestamp is not a
            real date, or the status code is outside 100-599.
    """
    text = line.rstrip("\r\n")
    match = LOG_LINE.fullmatch(text)
    if match is None:
        raise LogParseError("line does not match the access-log format (Common or Combined)")
    timestamp = parse_timestamp(match["timestamp"])
    status = int(match["status"])
    if not 100 <= status <= 599:
        raise LogParseError(f"invalid status code {status}")
    size = 0 if match["size"] == "-" else int(match["size"])
    return LogRecord(
        ip=match["ip"],
        timestamp=timestamp,
        method=match["method"],
        path=match["path"],
        protocol=match["protocol"],
        status=status,
        size=size,
        referrer=_optional(match["referrer"]),
        user_agent=_optional(match["user_agent"]),
    )


# ---------------------------------------------------------------------------
# Milestone 2: streaming pipeline
# ---------------------------------------------------------------------------


def read_lines(path: str | Path) -> Iterator[str]:
    """Yield the lines of a text file one at a time, without line endings.

    The file is opened on the first ``next()``, not when the function is called.
    ``utf-8-sig`` reads UTF-8 with or without a byte-order mark (Windows PowerShell 5.1
    writes one), and undecodable bytes become U+FFFD instead of crashing the run:
    logs often contain bytes sent by misbehaving clients.
    """
    with open(path, encoding="utf-8-sig", errors="replace") as file:
        for line in file:
            yield line.rstrip("\r\n")


def parse_records(
    lines: Iterable[str],
    on_malformed: Callable[[MalformedLine], None] | None = None,
) -> Iterator[LogRecord]:
    """Lazily parse lines into records.

    Blank lines are skipped silently. Malformed lines are skipped too, and reported
    to ``on_malformed`` (if given) with their 1-based line number.
    """
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = parse_line(line)
        except LogParseError as exc:
            if on_malformed is not None:
                on_malformed(MalformedLine(number, exc.reason, line))
            continue
        yield record


def _require_aware(value: datetime | None, name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


def filter_records(
    records: Iterable[LogRecord],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Iterator[LogRecord]:
    """Keep records with ``since <= timestamp < until`` (either bound may be None).

    The bounds are validated immediately (not on the first ``next()``): naive
    datetimes raise ValueError because they cannot be compared with log times.
    """
    _require_aware(since, "since")
    _require_aware(until, "until")
    return (
        record
        for record in records
        if (since is None or record.timestamp >= since) and (until is None or record.timestamp < until)
    )


# ---------------------------------------------------------------------------
# Milestone 3: statistics
# ---------------------------------------------------------------------------


def strip_query(path: str) -> str:
    """Return the path without its query string: ``/search?q=x`` -> ``/search``."""
    return path.split("?", 1)[0]


def status_class(status: int) -> str:
    """Return the class of a status code: 404 -> ``"4xx"``."""
    return f"{status // 100}xx"


def hour_bucket(timestamp: datetime) -> datetime:
    """Return the start of the UTC hour containing ``timestamp``."""
    return timestamp.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


@dataclass
class _HourCounts:
    requests: int = 0
    errors: int = 0


@dataclass
class LogStats:
    """Running totals over a stream of records.

    Call :meth:`add` once per record and :meth:`add_malformed` once per bad line.
    Memory use depends on the number of distinct paths and hours, not on the number
    of lines, so arbitrarily large logs can be analysed.
    """

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
        if not 100 <= self.error_threshold <= 599:
            raise ValueError(
                f"error_threshold must be a status code from 100 to 599, not {self.error_threshold}"
            )
        if self.max_examples < 0:
            raise ValueError("max_examples cannot be negative")

    def is_error(self, record: LogRecord) -> bool:
        """True if the record's status counts as an error (status >= error_threshold)."""
        return record.status >= self.error_threshold

    def add(self, record: LogRecord) -> None:
        """Count one request."""
        self.requests += 1
        self.bytes_sent += record.size
        self.status_counts[record.status] += 1
        self.path_counts[strip_query(record.path)] += 1
        hour = self._hours.setdefault(hour_bucket(record.timestamp), _HourCounts())
        hour.requests += 1
        if self.is_error(record):
            hour.errors += 1

    def add_malformed(self, item: MalformedLine) -> None:
        """Count a malformed line, keeping only the first ``max_examples`` of them."""
        self.malformed += 1
        if len(self.malformed_examples) < self.max_examples:
            self.malformed_examples.append(item)

    @property
    def errors(self) -> int:
        """Total number of error responses."""
        return sum(hour.errors for hour in self._hours.values())

    @property
    def error_rate(self) -> float:
        """Errors as a fraction of all requests (0.0 when there are none)."""
        return self.errors / self.requests if self.requests else 0.0

    def status_classes(self) -> dict[str, int]:
        """Counts per status class, ordered ``1xx`` .. ``5xx``."""
        classes: Counter[str] = Counter()
        for status, count in self.status_counts.items():
            classes[status_class(status)] += count
        return dict(sorted(classes.items()))

    def top_paths(self, n: int) -> list[tuple[str, int]]:
        """The ``n`` most requested paths, most requested first, ties alphabetical.

        (``Counter.most_common`` breaks ties by insertion order, which would make the
        report depend on the order of the log lines.)
        """
        if n < 1:
            raise ValueError("n must be at least 1")
        ranked = sorted(self.path_counts.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:n]

    def hourly_error_rates(self) -> list[HourlyErrorRate]:
        """One entry per UTC hour that had requests, in time order."""
        return [
            HourlyErrorRate(hour, counts.requests, counts.errors)
            for hour, counts in sorted(self._hours.items())
        ]


def analyze(
    lines: Iterable[str],
    *,
    error_threshold: int = 500,
    since: datetime | None = None,
    until: datetime | None = None,
    max_examples: int = MAX_MALFORMED_EXAMPLES,
) -> LogStats:
    """Run the whole pipeline over ``lines`` in a single pass and return the totals."""
    stats = LogStats(error_threshold=error_threshold, max_examples=max_examples)
    records = parse_records(lines, on_malformed=stats.add_malformed)
    for record in filter_records(records, since=since, until=until):
        stats.add(record)
    return stats


# ---------------------------------------------------------------------------
# Milestone 4: reports and command line
# ---------------------------------------------------------------------------


def safe_excerpt(text: str, limit: int = EXCERPT_LENGTH) -> str:
    """Make untrusted log text safe to print in a terminal.

    Non-printable characters (such as the ESC of terminal escape sequences or a
    stray carriage return) are shown as escapes like ``\\x1b``, and long text is
    shortened to ``limit`` characters followed by ``...``.
    """
    shown = text if len(text) <= limit else text[:limit]
    escaped = "".join(ch if ch.isprintable() else ascii(ch)[1:-1] for ch in shown)
    return escaped + ("..." if len(text) > limit else "")


def _format_hour(hour: HourlyErrorRate) -> str:
    """One line of the per-hour table, e.g. ``2026-10-22 13:00  5 requests  1 errors  20.0%``."""
    return (
        f"  {hour.hour:%Y-%m-%d %H:00}  {hour.requests:>6,} requests"
        f"  {hour.errors:>5,} errors  {hour.rate:6.1%}"
    )


def format_report(stats: LogStats, *, top: int = 5, show_malformed: bool = False) -> str:
    """Return a plain-text report."""
    lines = [
        "Access log report",
        "=================",
        f"Requests:        {stats.requests:,}",
        f"Malformed lines: {stats.malformed:,}",
        f"Bytes sent:      {stats.bytes_sent:,}",
        f"Error rate:      {stats.error_rate:.1%} (status >= {stats.error_threshold})",
    ]
    if stats.requests == 0:
        lines.append("")
        lines.append("No requests to report.")
    else:
        lines += ["", "Status codes:"]
        lines += [f"  {status}  {count:>8,}" for status, count in sorted(stats.status_counts.items())]
        lines += ["", "Status classes:"]
        lines += [f"  {name}  {count:>8,}" for name, count in stats.status_classes().items()]
        lines += ["", f"Top {top} paths:"]
        lines += [f"  {path}  {count:,}" for path, count in stats.top_paths(top)]
        lines += ["", "Errors per hour (UTC):"]
        lines += [_format_hour(hour) for hour in stats.hourly_error_rates()]
    if show_malformed and stats.malformed_examples:
        lines += ["", f"Malformed lines (first {len(stats.malformed_examples)}):"]
        lines += [
            f"  line {item.line_number}: {item.reason}: {safe_excerpt(item.text)}"
            for item in stats.malformed_examples
        ]
    return "\n".join(lines)


def report_to_dict(stats: LogStats, *, top: int = 5) -> dict[str, Any]:
    """Return the report as JSON-serialisable data."""
    return {
        "requests": stats.requests,
        "malformed": stats.malformed,
        "bytes_sent": stats.bytes_sent,
        "error_threshold": stats.error_threshold,
        "error_rate": round(stats.error_rate, 4),
        "status_counts": {str(status): count for status, count in sorted(stats.status_counts.items())},
        "status_classes": stats.status_classes(),
        "top_paths": [{"path": path, "count": count} for path, count in stats.top_paths(top)]
        if stats.requests
        else [],
        "hourly": [
            {
                "hour": hour.hour.isoformat(),
                "requests": hour.requests,
                "errors": hour.errors,
                "error_rate": round(hour.rate, 4),
            }
            for hour in stats.hourly_error_rates()
        ],
        "malformed_examples": [
            {"line": item.line_number, "reason": item.reason} for item in stats.malformed_examples
        ],
    }


def parse_cli_datetime(value: str) -> datetime:
    """argparse type: an ISO 8601 date-time; without an offset it is taken as UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date-time {value!r}; use ISO format such as 2026-10-22T13:00+00:00"
        ) from None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def positive_int(value: str) -> int:
    """argparse type: a whole number of at least 1."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a whole number, not {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {number}")
    return number


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="log_analyzer",
        description="Summarise a web-server access log (Common or Combined Log Format).",
    )
    parser.add_argument("logfile", help="path to the access log, or - to read standard input")
    parser.add_argument(
        "--top", type=positive_int, default=5, help="number of top paths to show (default: 5)"
    )
    parser.add_argument(
        "--error-threshold",
        type=int,
        choices=[400, 500],
        default=500,
        help="lowest status code that counts as an error: 500 (server errors, default) or 400 (all errors)",
    )
    parser.add_argument("--since", type=parse_cli_datetime, help="count requests at or after this ISO time")
    parser.add_argument("--until", type=parse_cli_datetime, help="count requests before this ISO time")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--show-malformed",
        action="store_true",
        help=f"list the first {MAX_MALFORMED_EXAMPLES} malformed lines with their line numbers",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.since and args.until and args.since >= args.until:
        parser.error("--since must be earlier than --until")
    if args.logfile == "-":
        lines: Iterable[str] = (line.rstrip("\r\n") for line in sys.stdin)
    else:
        lines = read_lines(args.logfile)
    try:
        stats = analyze(lines, error_threshold=args.error_threshold, since=args.since, until=args.until)
    except OSError as exc:
        print(f"error: cannot read {args.logfile}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report_to_dict(stats, top=args.top), indent=2))
    else:
        print(format_report(stats, top=args.top, show_malformed=args.show_malformed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
