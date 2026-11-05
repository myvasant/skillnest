"""Tests for the logging-monitoring project, grouped by milestone.

Everything is deterministic: request durations come from a fake clock, request IDs
from a counter, and log lines are captured in an in-memory stream.
"""

import io
import itertools
import json
import logging
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from observability_app import (
    PROMETHEUS_CONTENT_TYPE,
    REQUEST_ID_HEADER,
    JsonFormatter,
    MetricsRegistry,
    build_json_logger,
    create_app,
    escape_label_value,
    format_value,
    is_valid_request_id,
    request_id_var,
    resolve_request_id,
)


class FakeClock:
    """Returns 100.0, 100.25, 100.5, ... - every request takes exactly ``step`` seconds."""

    def __init__(self, step: float = 0.25) -> None:
        self.now = 100.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def parse_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    """Every captured log line, parsed as JSON (fails loudly if a line is not JSON)."""
    lines = stream.getvalue().splitlines()
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pytest.fail(f"Every log line must be one JSON object; got {line!r}")
    return parsed


def access_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [line for line in parse_lines(stream) if line.get("message") == "request completed"]


@pytest.fixture
def log_stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def registry() -> MetricsRegistry:
    return MetricsRegistry()


@pytest.fixture
def app(registry: MetricsRegistry, log_stream: io.StringIO) -> FastAPI:
    ids = (f"generated-{n}" for n in itertools.count(1))
    logger = build_json_logger("test-app", stream=log_stream)
    return create_app(registry=registry, logger=logger, clock=FakeClock(0.25), id_factory=lambda: next(ids))


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def metric_lines(client: TestClient) -> list[str]:
    response = client.get("/metrics")
    assert response.status_code == 200, f"GET /metrics should return 200, got {response.status_code}"
    return response.text.splitlines()


def make_record(message: str, *args: object, level: int = logging.INFO) -> logging.LogRecord:
    record = logging.LogRecord("orders", level, __file__, 10, message, args or None, None)
    record.created = 1_700_000_000.5  # 2023-11-14T22:13:20.500Z, fixed so the test is deterministic
    return record


# ---------------------------------------------------------------------------
# Milestone 1 - structured JSON logs
# ---------------------------------------------------------------------------


class TestMilestone1JsonLogs:
    def test_formats_a_record_as_one_json_object(self) -> None:
        line = JsonFormatter().format(make_record("order %s shipped", "A-7"))
        assert "\n" not in line, "A log entry must be exactly one line."
        assert json.loads(line) == {
            "ts": "2023-11-14T22:13:20.500Z",
            "level": "INFO",
            "logger": "orders",
            "message": "order A-7 shipped",
            "request_id": None,
        }, "Core fields: ts (ISO 8601 UTC with milliseconds and Z), level, logger, message, request_id."

    def test_extra_fields_become_top_level_keys(self, log_stream: io.StringIO) -> None:
        logger = build_json_logger("shop", stream=log_stream)
        logger.warning("payment declined", extra={"order_id": "A-7", "amount_cents": 1999})
        (entry,) = parse_lines(log_stream)
        assert entry["level"] == "WARNING"
        assert entry["order_id"] == "A-7" and entry["amount_cents"] == 1999, "Include `extra=` fields."

    def test_core_fields_win_over_extra_fields(self, log_stream: io.StringIO) -> None:
        build_json_logger("shop", stream=log_stream).info("hello", extra={"level": "FAKE"})
        (entry,) = parse_lines(log_stream)
        assert entry["level"] == "INFO", "An extra field must not overwrite a core field."

    def test_newlines_in_messages_cannot_forge_log_lines(self, log_stream: io.StringIO) -> None:
        hostile = 'user said hi\n{"level": "CRITICAL", "message": "forged"}'
        build_json_logger("shop", stream=log_stream).info("comment: %s", hostile)
        entries = parse_lines(log_stream)
        assert len(entries) == 1, "JSON escaping should keep a hostile message on one line."
        assert entries[0]["message"] == f"comment: {hostile}"

    def test_exceptions_are_structured(self, log_stream: io.StringIO) -> None:
        logger = build_json_logger("shop", stream=log_stream)
        try:
            raise ValueError("bad quantity")
        except ValueError:
            logger.exception("could not parse order")
        (entry,) = parse_lines(log_stream)
        assert entry["level"] == "ERROR"
        assert entry["exc_type"] == "ValueError" and entry["exc_message"] == "bad quantity"
        assert "Traceback" in entry["stack"], "Include the formatted traceback as `stack`."

    def test_request_id_comes_from_the_context(self) -> None:
        token = request_id_var.set("req-123")
        try:
            line = JsonFormatter().format(make_record("inside a request"))
        finally:
            request_id_var.reset(token)
        assert json.loads(line)["request_id"] == "req-123", "Read the ID from request_id_var."

    def test_build_json_logger_does_not_touch_the_global_registry(self) -> None:
        logger = build_json_logger("gw-private-logger", stream=io.StringIO())
        assert "gw-private-logger" not in logging.root.manager.loggerDict, (
            "Construct logging.Logger(name) directly instead of logging.getLogger(name)."
        )
        assert isinstance(logger.handlers[0].formatter, JsonFormatter)


# ---------------------------------------------------------------------------
# Milestone 2 - request IDs and access logs
# ---------------------------------------------------------------------------


class TestMilestone2RequestIds:
    @pytest.mark.parametrize("value", ["abc-123", "a.b_c", "0f8fad5b-d9cb-469f", "x" * 64])
    def test_accepts_safe_ids(self, value: str) -> None:
        assert is_valid_request_id(value)

    @pytest.mark.parametrize("value", ["", "x" * 65, "has space", 'quote"', "new\nline", "café"])
    def test_rejects_unsafe_ids(self, value: str) -> None:
        assert not is_valid_request_id(value), f"{value!r} must be rejected (log injection / size)."

    def test_resolve_keeps_valid_ids_and_replaces_others(self) -> None:
        assert resolve_request_id("trace-42", lambda: "new") == "trace-42"
        assert resolve_request_id(None, lambda: "new") == "new"
        assert resolve_request_id("bad id", lambda: "new") == "new"

    def test_generates_an_id_and_returns_it_in_the_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get(REQUEST_ID_HEADER) == "generated-1", (
            "Echo the request ID in the X-Request-ID response header."
        )

    def test_reuses_a_valid_incoming_id(self, client: TestClient) -> None:
        response = client.get("/health", headers={REQUEST_ID_HEADER: "trace-42"})
        assert response.headers.get(REQUEST_ID_HEADER) == "trace-42"

    def test_replaces_an_unsafe_incoming_id(self, client: TestClient) -> None:
        response = client.get("/health", headers={REQUEST_ID_HEADER: 'x" admin="true'})
        assert response.headers.get(REQUEST_ID_HEADER) == "generated-1"

    def test_writes_one_access_log_line_per_request(
        self, client: TestClient, log_stream: io.StringIO
    ) -> None:
        client.get("/items/1?token=secret-value", headers={REQUEST_ID_HEADER: "abc"})
        lines = access_lines(log_stream)
        assert len(lines) == 1, f"Expected one 'request completed' line, got {len(lines)}."
        line = lines[0]
        expected = {
            "level": "INFO",
            "request_id": "abc",
            "method": "GET",
            "path": "/items/1",
            "route": "/items/{item_id}",
            "status": 200,
            "duration_ms": 250.0,
        }
        assert {key: line.get(key) for key in expected} == expected
        assert "secret-value" not in log_stream.getvalue(), "Never log query strings."

    def test_log_lines_inside_handlers_carry_the_request_id(
        self, client: TestClient, log_stream: io.StringIO
    ) -> None:
        client.get("/items/2", headers={REQUEST_ID_HEADER: "abc"})
        inner = [line for line in parse_lines(log_stream) if line.get("message") == "item looked up"]
        assert inner and inner[0]["request_id"] == "abc", "Handler logs should get the ID from the context."
        assert inner[0]["item_id"] == 2

    def test_client_errors_log_at_warning(self, client: TestClient, log_stream: io.StringIO) -> None:
        assert client.get("/items/999").status_code == 404
        assert access_lines(log_stream)[0]["level"] == "WARNING"

    def test_unhandled_errors_become_a_logged_500(self, app: FastAPI, log_stream: io.StringIO) -> None:
        @app.get("/boom")
        def boom() -> None:
            raise RuntimeError("database unavailable")

        with TestClient(app, raise_server_exceptions=False) as test_client:
            response = test_client.get("/boom", headers={REQUEST_ID_HEADER: "err-1"})
        assert response.status_code == 500
        assert response.headers.get(REQUEST_ID_HEADER) == "err-1"
        assert response.json() == {"detail": "Internal Server Error", "request_id": "err-1"}
        errors = [line for line in parse_lines(log_stream) if line.get("exc_type") == "RuntimeError"]
        assert errors and errors[0]["request_id"] == "err-1", "Log the exception with the request ID."
        assert access_lines(log_stream)[0]["status"] == 500
        assert access_lines(log_stream)[0]["level"] == "ERROR"


# ---------------------------------------------------------------------------
# Milestone 3 - counters in the Prometheus text format
# ---------------------------------------------------------------------------


class TestMilestone3Counters:
    @pytest.mark.parametrize(
        ("value", "text"),
        [(3, "3.0"), (0.25, "0.25"), (1e-07, "1e-07"), (float("inf"), "+Inf"), (float("-inf"), "-Inf")],
    )
    def test_format_value(self, value: float, text: str) -> None:
        assert format_value(value) == text

    def test_escape_label_value(self) -> None:
        assert escape_label_value('say "hi"\\\n') == 'say \\"hi\\"\\\\\\n'

    def test_unlabelled_counter_starts_at_zero(self, registry: MetricsRegistry) -> None:
        registry.counter("jobs_total", "Jobs run.")
        assert registry.render() == "# HELP jobs_total Jobs run.\n# TYPE jobs_total counter\njobs_total 0.0\n"

    def test_labelled_counter_renders_sorted_series(self, registry: MetricsRegistry) -> None:
        counter = registry.counter("jobs_processed_total", "Jobs processed.", ["queue", "outcome"])
        counter.inc(queue="sms", outcome="failed")
        counter.inc(queue="emails", outcome="ok")
        counter.inc(2, queue="emails", outcome="ok")
        assert counter.value(queue="emails", outcome="ok") == 3.0
        assert registry.render() == (
            "# HELP jobs_processed_total Jobs processed.\n"
            "# TYPE jobs_processed_total counter\n"
            'jobs_processed_total{queue="emails",outcome="ok"} 3.0\n'
            'jobs_processed_total{queue="sms",outcome="failed"} 1.0\n'
        ), "Labels in declared order; series sorted by label values; one sample per line."

    def test_label_values_and_help_are_escaped(self, registry: MetricsRegistry) -> None:
        counter = registry.counter("errors_total", "Errors\nby kind.", ["kind"])
        counter.inc(kind='bad "quote"')
        assert registry.render().splitlines() == [
            "# HELP errors_total Errors\\nby kind.",
            "# TYPE errors_total counter",
            'errors_total{kind="bad \\"quote\\""} 1.0',
        ]

    def test_counter_rejects_decrements_and_wrong_labels(self, registry: MetricsRegistry) -> None:
        counter = registry.counter("jobs_total", "Jobs run.", ["queue"])
        with pytest.raises(ValueError):
            counter.inc(-1, queue="a")
        with pytest.raises(ValueError):
            counter.inc(queue="a", extra="b")
        with pytest.raises(ValueError):
            counter.inc()

    def test_registry_rejects_bad_names_and_duplicates(self, registry: MetricsRegistry) -> None:
        with pytest.raises(ValueError):
            registry.counter("http-requests", "Dashes are not allowed in metric names.")
        with pytest.raises(ValueError):
            registry.counter("ok_total", "Bad label name.", ["1st"])
        registry.counter("jobs_total", "Jobs run.")
        with pytest.raises(ValueError):
            registry.counter("jobs_total", "Registered twice.")


# ---------------------------------------------------------------------------
# Milestone 4 - histograms
# ---------------------------------------------------------------------------


class TestMilestone4Histograms:
    def test_renders_cumulative_buckets_sum_and_count(self, registry: MetricsRegistry) -> None:
        histogram = registry.histogram("job_seconds", "Job duration.", buckets=[0.1, 0.5, 1.0])
        for value in (0.0625, 0.25, 0.25, 2.0):
            histogram.observe(value)
        assert registry.render() == (
            "# HELP job_seconds Job duration.\n"
            "# TYPE job_seconds histogram\n"
            'job_seconds_bucket{le="0.1"} 1.0\n'
            'job_seconds_bucket{le="0.5"} 3.0\n'
            'job_seconds_bucket{le="1.0"} 3.0\n'
            'job_seconds_bucket{le="+Inf"} 4.0\n'
            "job_seconds_sum 2.5625\n"
            "job_seconds_count 4.0\n"
        ), "Buckets are cumulative (le = less than or equal) and end with +Inf."

    def test_a_value_on_a_boundary_counts_in_that_bucket(self, registry: MetricsRegistry) -> None:
        histogram = registry.histogram("job_seconds", "Job duration.", buckets=[0.5, 1.0])
        histogram.observe(0.5)
        assert 'job_seconds_bucket{le="0.5"} 1.0' in registry.render().splitlines()

    def test_labelled_histogram_puts_le_last(self, registry: MetricsRegistry) -> None:
        histogram = registry.histogram("rpc_seconds", "RPC latency.", ["service"], buckets=[1.0])
        histogram.observe(0.5, service="search")
        histogram.observe(1.5, service="auth")
        assert registry.render().splitlines()[2:] == [
            'rpc_seconds_bucket{service="auth",le="1.0"} 0.0',
            'rpc_seconds_bucket{service="auth",le="+Inf"} 1.0',
            'rpc_seconds_sum{service="auth"} 1.5',
            'rpc_seconds_count{service="auth"} 1.0',
            'rpc_seconds_bucket{service="search",le="1.0"} 1.0',
            'rpc_seconds_bucket{service="search",le="+Inf"} 1.0',
            'rpc_seconds_sum{service="search"} 0.5',
            'rpc_seconds_count{service="search"} 1.0',
        ]

    @pytest.mark.parametrize("buckets", [[], [0.5, 0.1], [0.1, 0.1]])
    def test_rejects_bad_buckets(self, registry: MetricsRegistry, buckets: list[float]) -> None:
        with pytest.raises(ValueError):
            registry.histogram("job_seconds", "Job duration.", buckets=buckets)

    def test_rejects_le_label_and_nan(self, registry: MetricsRegistry) -> None:
        with pytest.raises(ValueError):
            registry.histogram("a_seconds", "Reserved label.", ["le"])
        histogram = registry.histogram("b_seconds", "Duration.", buckets=[1.0])
        with pytest.raises(ValueError):
            histogram.observe(float("nan"))


# ---------------------------------------------------------------------------
# Milestone 5 - the /metrics endpoint and request metrics
# ---------------------------------------------------------------------------

SAMPLE_LINE = re.compile(r'[a-zA-Z_:][a-zA-Z0-9_:]*(\{([a-zA-Z_][a-zA-Z0-9_]*="([^"\\]|\\.)*",?)*\})? \S+')


class TestMilestone5MetricsEndpoint:
    def test_metrics_endpoint_uses_the_prometheus_content_type(self, client: TestClient) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == PROMETHEUS_CONTENT_TYPE

    def test_requests_are_counted_by_route_template(self, client: TestClient) -> None:
        for path in ("/items/1", "/items/2", "/items/999"):
            client.get(path)
        lines = metric_lines(client)
        assert 'http_requests_total{method="GET",path="/items/{item_id}",status="200"} 2.0' in lines
        assert 'http_requests_total{method="GET",path="/items/{item_id}",status="404"} 1.0' in lines
        assert not any('path="/items/1"' in line for line in lines), (
            "Label with the route template, not the raw path (unbounded cardinality)."
        )

    def test_unknown_paths_share_one_label(self, client: TestClient) -> None:
        client.get("/wp-admin")
        client.get("/.env")
        assert 'http_requests_total{method="GET",path="unmatched",status="404"} 2.0' in metric_lines(client)

    def test_latency_histogram_uses_the_injected_clock(self, client: TestClient) -> None:
        client.get("/health")
        client.get("/health")
        lines = metric_lines(client)
        for expected in (
            'http_request_duration_seconds_bucket{method="GET",path="/health",le="0.1"} 0.0',
            'http_request_duration_seconds_bucket{method="GET",path="/health",le="0.25"} 2.0',
            'http_request_duration_seconds_bucket{method="GET",path="/health",le="+Inf"} 2.0',
            'http_request_duration_seconds_sum{method="GET",path="/health"} 0.5',
            'http_request_duration_seconds_count{method="GET",path="/health"} 2.0',
        ):
            assert expected in lines, f"Missing {expected!r} - measure with the injected clock."

    def test_server_errors_are_counted(self, app: FastAPI) -> None:
        @app.get("/boom")
        def boom() -> None:
            raise RuntimeError("oops")

        with TestClient(app, raise_server_exceptions=False) as test_client:
            test_client.get("/boom")
            lines = metric_lines(test_client)
        assert 'http_requests_total{method="GET",path="/boom",status="500"} 1.0' in lines

    def test_exposition_is_well_formed(self, client: TestClient) -> None:
        client.get("/items/1")
        lines = metric_lines(client)
        declared: dict[str, str] = {}
        for line in lines:
            if line.startswith("# TYPE "):
                _, _, name, kind = line.split(" ")
                declared[name] = kind
            elif not line.startswith("# HELP "):
                assert SAMPLE_LINE.fullmatch(line), f"Not a valid sample line: {line!r}"
                family = re.sub(r"_(bucket|sum|count)$", "", line.split("{")[0].split(" ")[0])
                assert family in declared or line.split("{")[0].split(" ")[0] in declared, (
                    f"Sample {line!r} appears before its # TYPE line."
                )
        assert declared == {"http_requests_total": "counter", "http_request_duration_seconds": "histogram"}
