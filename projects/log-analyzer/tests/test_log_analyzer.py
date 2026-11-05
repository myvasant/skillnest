"""Behaviour tests for log_analyzer, one class per milestone.

Run one milestone with ``python -m pytest -k Milestone1``. Every test is
deterministic: log files live in ``tmp_path`` and all times are fixed.
"""

from __future__ import annotations

import inspect
import io
import itertools
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from log_analyzer import (
    HourlyErrorRate,
    LogParseError,
    LogRecord,
    LogStats,
    MalformedLine,
    analyze,
    filter_records,
    format_report,
    hour_bucket,
    main,
    parse_line,
    parse_records,
    read_lines,
    report_to_dict,
    safe_excerpt,
    status_class,
    strip_query,
)

COMMON = '198.51.100.23 - alice [22/Oct/2026:13:17:45 +0000] "POST /api/orders HTTP/1.1" 201 512'
COMBINED = (
    '203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html?ref=mail HTTP/1.1" 200 2326 '
    '"https://example.org/" "Mozilla/5.0 (X11; Linux x86_64)"'
)

# 12 lines: 9 requests, 1 blank line, 2 malformed lines (numbers 5 and 12).
SAMPLE_LOG = """\
203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"
203.0.113.7 - - [22/Oct/2026:13:05:02 +0000] "GET /style.css HTTP/1.1" 304 - "https://example.org/" "curl/8.5"
198.51.100.23 - alice [22/Oct/2026:13:17:45 +0000] "POST /api/orders HTTP/1.1" 201 512
198.51.100.23 - alice [22/Oct/2026:13:18:10 +0000] "GET /api/orders?page=2 HTTP/1.1" 500 87
this line is not a log entry
192.0.2.44 - - [22/Oct/2026:13:59:59 +0000] "GET /index.html HTTP/1.1" 200 2326

192.0.2.44 - - [22/Oct/2026:14:00:00 +0000] "GET /missing HTTP/1.1" 404 153
203.0.113.9 - - [22/Oct/2026:16:30:00 +0200] "GET /index.html HTTP/2.0" 200 2326 "-" "curl/8.5.0"
203.0.113.9 - - [22/Oct/2026:14:31:00 +0000] "GET /api/orders HTTP/1.1" 503 0
2001:db8::1 - - [22/Oct/2026:14:45:12 +0000] "DELETE /api/orders/7 HTTP/1.1" 204 -
192.0.2.50 - - [32/Oct/2026:14:50:00 +0000] "GET / HTTP/1.1" 200 10
"""

HOUR_13 = datetime(2026, 10, 22, 13, tzinfo=UTC)
HOUR_14 = datetime(2026, 10, 22, 14, tzinfo=UTC)


@pytest.fixture
def sample_lines() -> list[str]:
    """The sample log as a list of lines (what read_lines would yield)."""
    return SAMPLE_LOG.splitlines()


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    """The sample log written to a file in a temporary folder."""
    path = tmp_path / "access.log"
    path.write_text(SAMPLE_LOG, encoding="utf-8")
    return path


def normalised_lines(text: str) -> list[str]:
    """Collapse runs of spaces so tests do not depend on column alignment."""
    return [" ".join(line.split()) for line in text.splitlines()]


def make_record(status: int = 200, path: str = "/", when: datetime = HOUR_13, size: int = 100) -> LogRecord:
    return LogRecord(
        ip="192.0.2.1", timestamp=when, method="GET", path=path, protocol="HTTP/1.1", status=status, size=size
    )


class TestMilestone1Parsing:
    """parse_line turns one line into a LogRecord or raises LogParseError."""

    def test_parses_common_log_format(self) -> None:
        record = parse_line(COMMON)
        assert record == LogRecord(
            ip="198.51.100.23",
            timestamp=datetime(2026, 10, 22, 13, 17, 45, tzinfo=UTC),
            method="POST",
            path="/api/orders",
            protocol="HTTP/1.1",
            status=201,
            size=512,
            referrer=None,
            user_agent=None,
        )

    def test_parses_combined_log_format(self) -> None:
        record = parse_line(COMBINED)
        assert record.path == "/index.html?ref=mail", "the path keeps its query string"
        assert record.referrer == "https://example.org/"
        assert record.user_agent == "Mozilla/5.0 (X11; Linux x86_64)"

    def test_timestamp_is_timezone_aware(self) -> None:
        line = COMMON.replace("+0000", "+0530")
        record = parse_line(line)
        assert record.timestamp.utcoffset() == timedelta(hours=5, minutes=30)
        assert record.timestamp == datetime(2026, 10, 22, 7, 47, 45, tzinfo=UTC)

    def test_dash_size_means_zero_and_dash_referrer_means_none(self) -> None:
        line = '192.0.2.1 - - [22/Oct/2026:10:00:00 +0000] "GET /a HTTP/1.1" 304 - "-" "-"'
        record = parse_line(line)
        assert record.size == 0
        assert record.referrer is None and record.user_agent is None

    def test_ipv6_address_and_windows_line_ending(self) -> None:
        line = '2001:db8::1 - - [22/Oct/2026:10:00:00 +0000] "DELETE /api/orders/7 HTTP/2.0" 204 -\r\n'
        record = parse_line(line)
        assert record.ip == "2001:db8::1"
        assert record.protocol == "HTTP/2.0"

    def test_escaped_quotes_inside_user_agent(self) -> None:
        line = (
            '192.0.2.1 - - [22/Oct/2026:10:00:00 +0000] "GET / HTTP/1.1" 200 5 "-" "Bot \\"quoted\\" agent"'
        )
        assert parse_line(line).user_agent == 'Bot \\"quoted\\" agent'

    def test_record_is_immutable(self) -> None:
        record = parse_line(COMMON)
        with pytest.raises(AttributeError):
            record.status = 500  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("line", "reason"),
        [
            pytest.param("", "format", id="empty"),
            pytest.param("garbage", "format", id="garbage"),
            pytest.param(COMMON.replace('1.1"', "1.1"), "format", id="missing-quote"),
            pytest.param(COMMON.replace(" 201 ", " abc "), "format", id="status-not-digits"),
            pytest.param(COMMON.replace(" 512", " 12k"), "format", id="size-not-digits"),
            pytest.param(
                COMMON.replace('"POST /api/orders HTTP/1.1"', '"-"'), "format", id="no-request-line"
            ),
            pytest.param(COMMON.replace("22/Oct", "32/Oct"), "timestamp", id="day-32"),
            pytest.param(COMMON.replace("Oct", "Foo"), "timestamp", id="bad-month"),
            pytest.param(COMMON.replace(" +0000", ""), "timestamp", id="no-timezone"),
            pytest.param(COMMON.replace(" 201 ", " 999 "), "status", id="status-out-of-range"),
        ],
    )
    def test_malformed_lines_raise_with_a_reason(self, line: str, reason: str) -> None:
        with pytest.raises(LogParseError) as excinfo:
            parse_line(line)
        assert reason in excinfo.value.reason
        assert isinstance(excinfo.value, ValueError), "LogParseError should be a ValueError subclass"


class TestMilestone2Streaming:
    """read_lines, parse_records and filter_records are lazy generators."""

    def test_read_lines_yields_lines_without_endings(self, log_file: Path) -> None:
        lines = read_lines(log_file)
        assert inspect.isgenerator(lines), "read_lines should be a generator function (use yield)"
        assert list(lines) == SAMPLE_LOG.splitlines()

    def test_read_lines_opens_the_file_lazily(self, tmp_path: Path) -> None:
        lines = read_lines(tmp_path / "missing.log")  # no error yet: nothing has been read
        with pytest.raises(FileNotFoundError):
            next(lines)

    def test_read_lines_survives_undecodable_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "binary.log"
        path.write_bytes(b"ok line\n\xff\xfe broken\r\nlast")
        assert list(read_lines(path)) == ["ok line", "�� broken", "last"]

    def test_read_lines_ignores_a_byte_order_mark(self, tmp_path: Path) -> None:
        path = tmp_path / "bom.log"
        path.write_bytes(b"\xef\xbb\xbf" + COMMON.encode("utf-8") + b"\n")
        assert list(read_lines(path)) == [COMMON], "open the file with encoding='utf-8-sig'"

    def test_parse_records_skips_blank_and_reports_malformed(self, sample_lines: list[str]) -> None:
        bad: list[MalformedLine] = []
        records = list(parse_records(sample_lines, on_malformed=bad.append))
        assert len(records) == 9
        assert [item.line_number for item in bad] == [5, 12]
        assert bad[0].text == "this line is not a log entry"
        assert "timestamp" in bad[1].reason

    def test_parse_records_without_callback_just_skips(self, sample_lines: list[str]) -> None:
        assert len(list(parse_records(sample_lines))) == 9

    def test_parse_records_is_lazy(self) -> None:
        produced = 0

        def endless_log():
            nonlocal produced
            while True:
                produced += 1
                yield COMMON

        first_three = list(itertools.islice(parse_records(endless_log()), 3))
        assert len(first_three) == 3
        assert produced == 3, "parse_records must not read ahead: it should pull one line per record"

    def test_filter_records_since_inclusive_until_exclusive(self, sample_lines: list[str]) -> None:
        records = list(parse_records(sample_lines))
        after = list(filter_records(records, since=HOUR_14))
        before = list(filter_records(records, until=HOUR_14))
        assert len(after) == 4 and len(before) == 5
        assert all(r.timestamp >= HOUR_14 for r in after)
        window = list(filter_records(records, since=HOUR_13, until=HOUR_13 + timedelta(minutes=18)))
        assert [r.path for r in window] == ["/index.html", "/style.css", "/api/orders"]

    def test_filter_records_compares_across_timezones(self) -> None:
        plus_two = timezone(timedelta(hours=2))
        record = make_record(when=datetime(2026, 10, 22, 16, 30, tzinfo=plus_two))  # 14:30 UTC
        assert list(filter_records([record], since=HOUR_14)) == [record]

    def test_filter_records_rejects_naive_datetimes_immediately(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            filter_records([], since=datetime(2026, 10, 22, 14))


class TestMilestone3Statistics:
    """LogStats accumulates totals in one pass; analyze runs the whole pipeline."""

    def test_counts_requests_bytes_and_statuses(self, sample_lines: list[str]) -> None:
        stats = analyze(sample_lines)
        assert stats.requests == 9
        assert stats.malformed == 2
        assert stats.bytes_sent == 7730
        assert stats.status_counts == {200: 3, 304: 1, 201: 1, 500: 1, 404: 1, 503: 1, 204: 1}

    @pytest.mark.parametrize(
        ("status", "expected"), [(200, "2xx"), (204, "2xx"), (304, "3xx"), (404, "4xx"), (503, "5xx")]
    )
    def test_status_class(self, status: int, expected: str) -> None:
        assert status_class(status) == expected

    def test_status_classes_are_ordered(self, sample_lines: list[str]) -> None:
        classes = analyze(sample_lines).status_classes()
        assert classes == {"2xx": 5, "3xx": 1, "4xx": 1, "5xx": 2}
        assert list(classes) == ["2xx", "3xx", "4xx", "5xx"]

    def test_top_paths_strip_query_and_break_ties_alphabetically(self, sample_lines: list[str]) -> None:
        stats = analyze(sample_lines)
        assert stats.top_paths(2) == [("/api/orders", 3), ("/index.html", 3)]
        assert stats.top_paths(10) == [
            ("/api/orders", 3),
            ("/index.html", 3),
            ("/api/orders/7", 1),
            ("/missing", 1),
            ("/style.css", 1),
        ]
        with pytest.raises(ValueError):
            stats.top_paths(0)

    def test_top_paths_do_not_depend_on_line_order(self) -> None:
        forward, backward = LogStats(), LogStats()
        records = [make_record(path=p) for p in ["/b", "/a", "/c", "/a", "/b"]]
        for record in records:
            forward.add(record)
        for record in reversed(records):
            backward.add(record)
        assert forward.top_paths(3) == backward.top_paths(3) == [("/a", 2), ("/b", 2), ("/c", 1)]

    @pytest.mark.parametrize("path", ["/search?q=x", "/search", "/search?"])
    def test_strip_query(self, path: str) -> None:
        assert strip_query(path) == "/search"

    def test_hour_bucket_uses_utc(self) -> None:
        plus_two = timezone(timedelta(hours=2))
        assert hour_bucket(datetime(2026, 10, 22, 16, 59, 59, tzinfo=plus_two)) == datetime(
            2026, 10, 22, 14, tzinfo=UTC
        )

    def test_hourly_error_rates_with_default_threshold(self, sample_lines: list[str]) -> None:
        stats = analyze(sample_lines)
        assert stats.hourly_error_rates() == [
            HourlyErrorRate(HOUR_13, requests=5, errors=1),
            HourlyErrorRate(HOUR_14, requests=4, errors=1),
        ]
        assert stats.hourly_error_rates()[0].rate == pytest.approx(0.2)
        assert stats.error_rate == pytest.approx(2 / 9)

    def test_threshold_400_counts_client_errors(self, sample_lines: list[str]) -> None:
        stats = analyze(sample_lines, error_threshold=400)
        assert [h.errors for h in stats.hourly_error_rates()] == [1, 2]
        assert stats.error_rate == pytest.approx(3 / 9)

    def test_since_and_until_limit_the_analysis(self, sample_lines: list[str]) -> None:
        assert analyze(sample_lines, since=HOUR_14).requests == 4
        assert analyze(sample_lines, until=HOUR_14).requests == 5

    def test_empty_input_has_zero_error_rate(self) -> None:
        stats = analyze([])
        assert (stats.requests, stats.error_rate, stats.hourly_error_rates()) == (0, 0.0, [])

    def test_malformed_examples_are_bounded(self) -> None:
        stats = LogStats(max_examples=2)
        for number in range(1, 6):
            stats.add_malformed(MalformedLine(number, "bad", "x"))
        assert stats.malformed == 5
        assert [item.line_number for item in stats.malformed_examples] == [1, 2]

    @pytest.mark.parametrize("threshold", [0, 99, 600])
    def test_invalid_threshold_is_rejected(self, threshold: int) -> None:
        with pytest.raises(ValueError, match="error_threshold"):
            LogStats(error_threshold=threshold)


class TestMilestone4ReportAndCli:
    """format_report, report_to_dict and main() produce the user-facing output."""

    def test_text_report_contents(self, sample_lines: list[str]) -> None:
        lines = normalised_lines(format_report(analyze(sample_lines), top=3))
        for expected in [
            "Requests: 9",
            "Malformed lines: 2",
            "Bytes sent: 7,730",
            "Error rate: 22.2% (status >= 500)",
            "200 3",
            "5xx 2",
            "Top 3 paths:",
            "/api/orders 3",
            "/index.html 3",
            "/api/orders/7 1",
            "2026-10-22 13:00 5 requests 1 errors 20.0%",
            "2026-10-22 14:00 4 requests 1 errors 25.0%",
        ]:
            assert expected in lines
        assert "/missing 1" not in lines, "only the top 3 paths are listed"

    def test_report_for_an_empty_log(self) -> None:
        text = format_report(analyze([]))
        assert "No requests to report." in text

    def test_report_to_dict_is_json_ready(self, sample_lines: list[str]) -> None:
        data = report_to_dict(analyze(sample_lines), top=1)
        assert json.loads(json.dumps(data)) == data
        assert data["requests"] == 9 and data["malformed"] == 2
        assert data["status_counts"]["503"] == 1
        assert data["top_paths"] == [{"path": "/api/orders", "count": 3}]
        assert data["hourly"][1] == {
            "hour": "2026-10-22T14:00:00+00:00",
            "requests": 4,
            "errors": 1,
            "error_rate": 0.25,
        }
        assert data["malformed_examples"][0]["line"] == 5

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param("plain text", "plain text", id="unchanged"),
            pytest.param("evil \x1b[31mred", "evil \\x1b[31mred", id="escape-sequence"),
            pytest.param("a\rb\tc", "a\\rb\\tc", id="control-characters"),
            pytest.param("x" * 100, "x" * 80 + "...", id="truncated"),
        ],
    )
    def test_safe_excerpt(self, text: str, expected: str) -> None:
        assert safe_excerpt(text) == expected

    def test_cli_text_report(self, log_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(log_file), "--top", "1"]) == 0
        lines = normalised_lines(capsys.readouterr().out)
        assert "Requests: 9" in lines and "Top 1 paths:" in lines and "/api/orders 3" in lines
        assert "/index.html 3" not in lines

    def test_cli_json_and_threshold(self, log_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(log_file), "--json", "--error-threshold", "400"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["error_threshold"] == 400
        assert data["error_rate"] == pytest.approx(0.3333, abs=1e-4)

    def test_cli_time_window(self, log_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # A naive --since is taken as UTC; 16:31+02:00 is 14:31 UTC, and --until is exclusive,
        # so only the requests at 14:00:00 and 14:30 UTC are inside the window.
        assert (
            main(
                [str(log_file), "--json", "--since", "2026-10-22T14:00", "--until", "2026-10-22T16:31+02:00"]
            )
            == 0
        )
        data = json.loads(capsys.readouterr().out)
        assert data["requests"] == 2

    def test_cli_show_malformed_escapes_control_characters(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "evil.log"
        path.write_text(COMMON + "\n\x1b[2Jhello\n", encoding="utf-8")
        assert main([str(path), "--show-malformed"]) == 0
        out = capsys.readouterr().out
        assert "line 2:" in out and "\\x1b[2Jhello" in out
        assert "\x1b" not in out, "raw escape characters from the log must never reach the terminal"

    def test_cli_reads_standard_input(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(SAMPLE_LOG))
        assert main(["-", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["requests"] == 9

    def test_cli_missing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(tmp_path / "nope.log")]) == 1
        captured = capsys.readouterr()
        assert captured.err.startswith("error: cannot read")
        assert captured.out == ""

    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(["--top", "0"], id="top-zero"),
            pytest.param(["--error-threshold", "450"], id="bad-threshold"),
            pytest.param(["--since", "yesterday"], id="bad-date"),
            pytest.param(["--since", "2026-10-22T15:00", "--until", "2026-10-22T14:00"], id="empty-window"),
        ],
    )
    def test_cli_usage_errors_exit_with_code_2(self, log_file: Path, args: list[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([str(log_file), *args])
        assert excinfo.value.code == 2
