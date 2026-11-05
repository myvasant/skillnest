"""observability_app: structured JSON logs, request IDs and Prometheus metrics for FastAPI.

Three production habits in one small service:

* **Structured logs** - every log line is one JSON object (``JsonFormatter``), so a log
  platform can filter on ``status`` or ``request_id`` instead of grepping text.
* **Request IDs** - a middleware gives every request an ID (reusing a safe incoming
  ``X-Request-ID``), stores it in a ``ContextVar`` so *every* log line written while
  handling the request carries it, and echoes it in the response header.
* **Metrics** - a hand-written registry of counters and histograms rendered in the
  Prometheus text exposition format at ``GET /metrics``.

Run it::

    python -m uvicorn --factory observability_app:create_app --port 8000
    curl -i -H "X-Request-ID: demo-1" http://127.0.0.1:8000/items/1
    curl http://127.0.0.1:8000/metrics
"""

import json
import logging
import math
import re
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self, TextIO, TypeVar

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

__all__ = [
    "DEFAULT_BUCKETS",
    "PROMETHEUS_CONTENT_TYPE",
    "REQUEST_ID_HEADER",
    "UNMATCHED_ROUTE",
    "Counter",
    "Histogram",
    "HttpMetrics",
    "JsonFormatter",
    "MetricsRegistry",
    "build_json_logger",
    "call_next_safely",
    "create_app",
    "current_request_id",
    "escape_label_value",
    "format_value",
    "is_valid_request_id",
    "log_request",
    "new_request_id",
    "record_request",
    "request_id_var",
    "resolve_request_id",
    "route_template",
]

REQUEST_ID_HEADER = "X-Request-ID"
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
DEFAULT_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
UNMATCHED_ROUTE = "unmatched"

_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_METRIC_NAME = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
_LABEL_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

# The ID of the request being handled in the *current context*. Each request runs in
# its own context, so concurrent requests never see each other's ID.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has. Anything else on a record was passed with ``extra=``.
_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}

CallNext = Callable[[Request], Awaitable[Response]]


# ---------------------------------------------------------------------------
# Milestone 1 - structured JSON logs
# ---------------------------------------------------------------------------


def current_request_id() -> str | None:
    """The request ID of the request being handled, or ``None`` outside a request."""
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """Format each log record as one JSON object on a single line.

    Core fields: ``ts`` (ISO 8601 UTC, from ``record.created``), ``level``, ``logger``,
    ``message`` and ``request_id``. Values passed with ``extra={...}`` are added as
    top-level fields (core fields win on a name clash). Exceptions add ``exc_type``,
    ``exc_message`` and ``stack``. ``json.dumps`` escapes newlines, so user input in a
    message can never start a fake log line.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return the JSON line for ``record``."""
        entry: dict[str, Any] = {
            "ts": _iso_utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or current_request_id(),
        }
        for key, value in _extra_fields(record).items():
            entry.setdefault(key, value)
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc_type"] = record.exc_info[0].__name__
            entry["exc_message"] = str(record.exc_info[1])
            entry["stack"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def _iso_utc(timestamp: float) -> str:
    """``1700000000.5`` -> ``"2023-11-14T22:13:20.500Z"``."""
    moment = datetime.fromtimestamp(timestamp, tz=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields a caller attached with ``extra=``."""
    return {k: v for k, v in vars(record).items() if k not in _RECORD_ATTRS and not k.startswith("_")}


def build_json_logger(
    name: str = "observability_app", stream: TextIO | None = None, level: int = logging.INFO
) -> logging.Logger:
    """Create a logger that writes JSON lines to ``stream`` (standard error by default).

    The logger is constructed directly instead of through ``logging.getLogger``, so it
    is not shared through the global logging registry: each app (and each test) owns
    its logger and nothing leaks between them.
    """
    logger = logging.Logger(name, level)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


# ---------------------------------------------------------------------------
# Milestone 2 - request IDs
# ---------------------------------------------------------------------------


def new_request_id() -> str:
    """A fresh, random, log-safe request ID (32 hex characters)."""
    return uuid.uuid4().hex


def is_valid_request_id(value: str) -> bool:
    """True if ``value`` is 1-64 characters of letters, digits, ``.``, ``_`` or ``-``.

    Incoming IDs end up in logs and response headers, so anything else (spaces,
    quotes, newlines, very long strings) is rejected to prevent log injection.
    """
    return bool(_REQUEST_ID.fullmatch(value))


def resolve_request_id(incoming: str | None, id_factory: Callable[[], str] = new_request_id) -> str:
    """Reuse a valid incoming ID (so traces join up across services), else make one."""
    if incoming is not None and is_valid_request_id(incoming):
        return incoming
    return id_factory()


async def call_next_safely(call_next: CallNext, request: Request, logger: logging.Logger) -> Response:
    """Run the rest of the app; turn an unhandled exception into a logged 500 response.

    The 500 body includes the request ID so a user can quote it to support, and the
    log line (with the stack trace) carries the same ID.
    """
    try:
        return await call_next(request)
    except Exception:
        logger.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        body = {"detail": "Internal Server Error", "request_id": current_request_id()}
        return JSONResponse(body, status_code=500)


def route_template(request: Request) -> str:
    """The matched route's template (``/items/{item_id}``), or ``"unmatched"``.

    Labelling metrics with the raw path would create one time series per item ID
    (or per scanner probe) - a cardinality explosion. Templates keep it bounded.
    The matched route is only in the scope *after* the app has handled the request.
    """
    route = request.scope.get("route")
    return getattr(route, "path", None) or UNMATCHED_ROUTE


def log_request(
    logger: logging.Logger, request: Request, route: str, status: int, duration_seconds: float
) -> None:
    """Write the access-log line for a finished request.

    Level: ERROR for 5xx, WARNING for 4xx, INFO otherwise. Only the URL *path* is
    logged - query strings often contain tokens or personal data.
    """
    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    fields = {
        "method": request.method,
        "path": request.url.path,
        "route": route,
        "status": status,
        "duration_ms": round(duration_seconds * 1000, 3),
    }
    logger.log(level, "request completed", extra=fields)


# ---------------------------------------------------------------------------
# Milestones 3 and 4 - metrics in the Prometheus text format
# ---------------------------------------------------------------------------


def format_value(value: float) -> str:
    """Format a sample value or bucket bound the way Prometheus client libraries do.

    ``3`` -> ``"3.0"``, ``0.25`` -> ``"0.25"``, ``inf`` -> ``"+Inf"``.
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return repr(float(value))


def escape_label_value(value: str) -> str:
    r"""Escape a label value: ``\`` -> ``\\``, ``"`` -> ``\"``, newline -> ``\n``."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _escape_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _render_labels(names: Sequence[str], values: Sequence[str]) -> str:
    """``("method", "path"), ("GET", "/")`` -> ``{method="GET",path="/"}``; empty -> ``""``."""
    if not names:
        return ""
    pairs = ",".join(f'{n}="{escape_label_value(v)}"' for n, v in zip(names, values, strict=True))
    return "{" + pairs + "}"


class _Metric:
    """Shared behaviour: name/label validation, label lookup and the HELP/TYPE header."""

    kind = "untyped"

    def __init__(self, name: str, help_text: str, labelnames: Sequence[str] = ()) -> None:
        if not _METRIC_NAME.fullmatch(name):
            raise ValueError(f"invalid metric name {name!r}")
        for label in labelnames:
            if not _LABEL_NAME.fullmatch(label) or label.startswith("__"):
                raise ValueError(f"invalid label name {label!r}")
        if len(set(labelnames)) != len(labelnames):
            raise ValueError(f"duplicate label names in {list(labelnames)}")
        self.name = name
        self.help_text = help_text
        self.labelnames = tuple(labelnames)
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> tuple[str, ...]:
        """The series key for ``labels``; every declared label must be given, no others."""
        if set(labels) != set(self.labelnames):
            raise ValueError(f"{self.name} expects labels {list(self.labelnames)}, got {sorted(labels)}")
        return tuple(str(labels[name]) for name in self.labelnames)

    def render(self) -> list[str]:
        """The ``# HELP`` and ``# TYPE`` lines followed by every sample line."""
        header = [f"# HELP {self.name} {_escape_help(self.help_text)}", f"# TYPE {self.name} {self.kind}"]
        with self._lock:
            return header + list(self._samples())

    def _samples(self) -> Iterator[str]:  # pragma: no cover - overridden
        raise NotImplementedError


class Counter(_Metric):
    """A value that only goes up (requests served, errors seen)."""

    kind = "counter"

    def __init__(self, name: str, help_text: str, labelnames: Sequence[str] = ()) -> None:
        super().__init__(name, help_text, labelnames)
        self._values: dict[tuple[str, ...], float] = {}
        if not self.labelnames:
            self._values[()] = 0.0  # an unlabelled counter is exported from the start

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Add ``amount`` (default 1) to the series identified by ``labels``."""
        if amount < 0:
            raise ValueError("counters only go up; use a gauge for values that can decrease")
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        """The current value of one series (0.0 if it was never incremented)."""
        key = self._key(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def _samples(self) -> Iterator[str]:
        for key in sorted(self._values):
            yield f"{self.name}{_render_labels(self.labelnames, key)} {format_value(self._values[key])}"


@dataclass
class _Series:
    """Observations of one histogram series: cumulative bucket counts, sum and count."""

    bucket_counts: list[int]
    total: float = 0.0
    count: int = 0


class Histogram(_Metric):
    """Counts observations (such as latencies) into cumulative ``le`` buckets."""

    kind = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        labelnames: Sequence[str] = (),
        buckets: Sequence[float] = DEFAULT_BUCKETS,
    ) -> None:
        super().__init__(name, help_text, labelnames)
        if "le" in self.labelnames:
            raise ValueError("'le' is reserved for histogram buckets")
        bounds = [float(b) for b in buckets]
        if not bounds or any(a >= b for a, b in zip(bounds, bounds[1:], strict=False)):
            raise ValueError("buckets must be a non-empty, strictly increasing sequence")
        if bounds[-1] != math.inf:
            bounds.append(math.inf)
        self.buckets = tuple(bounds)
        self._series: dict[tuple[str, ...], _Series] = {}
        if not self.labelnames:
            self._series[()] = self._new_series()

    def _new_series(self) -> _Series:
        return _Series(bucket_counts=[0] * len(self.buckets))

    def observe(self, value: float, **labels: str) -> None:
        """Record one observation in every bucket whose upper bound is >= ``value``."""
        if math.isnan(value):
            raise ValueError("cannot observe NaN")
        key = self._key(labels)
        with self._lock:
            series = self._series.setdefault(key, self._new_series())
            for index, bound in enumerate(self.buckets):
                if value <= bound:
                    series.bucket_counts[index] += 1
            series.total += value
            series.count += 1

    def _samples(self) -> Iterator[str]:
        bucket_labels = (*self.labelnames, "le")
        for key in sorted(self._series):
            series = self._series[key]
            for bound, count in zip(self.buckets, series.bucket_counts, strict=True):
                labels = _render_labels(bucket_labels, (*key, format_value(bound)))
                yield f"{self.name}_bucket{labels} {format_value(count)}"
            labels = _render_labels(self.labelnames, key)
            yield f"{self.name}_sum{labels} {format_value(series.total)}"
            yield f"{self.name}_count{labels} {format_value(series.count)}"


M = TypeVar("M", bound=_Metric)


class MetricsRegistry:
    """Owns the metrics of one app and renders them for ``GET /metrics``."""

    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}

    def counter(self, name: str, help_text: str, labelnames: Sequence[str] = ()) -> Counter:
        """Create and register a counter."""
        return self._register(Counter(name, help_text, labelnames))

    def histogram(
        self,
        name: str,
        help_text: str,
        labelnames: Sequence[str] = (),
        buckets: Sequence[float] = DEFAULT_BUCKETS,
    ) -> Histogram:
        """Create and register a histogram."""
        return self._register(Histogram(name, help_text, labelnames, buckets))

    def _register(self, metric: M) -> M:
        """Add ``metric``; names must be unique within a registry."""
        if metric.name in self._metrics:
            raise ValueError(f"metric {metric.name!r} is already registered")
        self._metrics[metric.name] = metric
        return metric

    def render(self) -> str:
        """Every metric, in registration order, in the Prometheus text format."""
        lines = [line for metric in self._metrics.values() for line in metric.render()]
        return "".join(f"{line}\n" for line in lines)


# ---------------------------------------------------------------------------
# Milestone 5 - wiring metrics into the app
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpMetrics:
    """The two metrics every HTTP service should have: traffic and latency."""

    requests: Counter
    latency: Histogram

    @classmethod
    def register(cls, registry: MetricsRegistry, buckets: Sequence[float] = DEFAULT_BUCKETS) -> Self:
        """Create both metrics in ``registry``."""
        return cls(
            requests=registry.counter(
                "http_requests_total",
                "HTTP requests handled, by method, route template and status code.",
                ("method", "path", "status"),
            ),
            latency=registry.histogram(
                "http_request_duration_seconds",
                "Time spent handling HTTP requests, in seconds.",
                ("method", "path"),
                buckets,
            ),
        )


def record_request(metrics: HttpMetrics, method: str, route: str, status: int, duration: float) -> None:
    """Count the request and observe its latency."""
    metrics.requests.inc(method=method, path=route, status=str(status))
    metrics.latency.observe(duration, method=method, path=route)


def create_app(
    *,
    registry: MetricsRegistry | None = None,
    logger: logging.Logger | None = None,
    clock: Callable[[], float] = time.perf_counter,
    id_factory: Callable[[], str] = new_request_id,
    buckets: Sequence[float] = DEFAULT_BUCKETS,
) -> FastAPI:
    """Build the app. Every collaborator is injectable so tests are deterministic.

    Args:
        registry: where metrics live (a fresh one by default).
        logger: the JSON logger (``build_json_logger()`` by default).
        clock: monotonic seconds, used only to measure request duration.
        id_factory: makes request IDs when the caller sends none (or an unsafe one).
        buckets: latency histogram bucket upper bounds, in seconds.
    """
    registry = registry if registry is not None else MetricsRegistry()
    log = logger if logger is not None else build_json_logger()
    metrics = HttpMetrics.register(registry, buckets)
    catalogue = {1: "keyboard", 2: "mouse", 3: "monitor"}
    app = FastAPI(title="Observability demo", version="1.0.0")

    @app.middleware("http")
    async def observe_requests(request: Request, call_next: CallNext) -> Response:
        """Give every request an ID, then log and measure it."""
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER), id_factory)
        token = request_id_var.set(request_id)
        try:
            start = clock()
            response = await call_next_safely(call_next, request, log)
            duration = clock() - start
            route = route_template(request)
            record_request(metrics, request.method, route, response.status_code, duration)
            log_request(log, request, route, response.status_code, duration)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(token)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness check."""
        return {"status": "ok"}

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict[str, Any]:
        """Look up an item; the log line inside carries the request ID automatically."""
        name = catalogue.get(item_id)
        log.info("item looked up", extra={"item_id": item_id, "found": name is not None})
        if name is None:
            raise HTTPException(status_code=404, detail=f"item {item_id} not found")
        return {"id": item_id, "name": name}

    @app.get("/metrics")
    def metrics_endpoint() -> Response:
        """All metrics in the Prometheus text exposition format (version 0.0.4)."""
        return Response(registry.render(), media_type=PROMETHEUS_CONTENT_TYPE)

    return app
