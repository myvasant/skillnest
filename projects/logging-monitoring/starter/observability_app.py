"""observability_app: structured JSON logs, request IDs and Prometheus metrics for FastAPI.

Three production habits in one small service:

* **Structured logs** - every log line is one JSON object (``JsonFormatter``).
* **Request IDs** - a middleware gives every request an ID, stores it in a
  ``ContextVar`` so every log line written during the request carries it, and echoes
  it in the ``X-Request-ID`` response header.
* **Metrics** - a hand-written registry of counters and histograms rendered in the
  Prometheus text exposition format at ``GET /metrics``.

Work through the milestones in order (``python -m pytest -k Milestone1`` ...). Each
TODO names its milestone. The wiring in ``create_app`` is provided; the middleware
body is yours to write.

Run it::

    python -m uvicorn --factory observability_app:create_app --port 8000
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

    Core fields: ``ts`` (ISO 8601 UTC with milliseconds and ``Z``, from
    ``record.created``), ``level``, ``logger``, ``message`` (``record.getMessage()``)
    and ``request_id`` (from the record, else ``current_request_id()``). Values passed
    with ``extra={...}`` become top-level fields, but core fields win on a name clash.
    Exceptions add ``exc_type``, ``exc_message`` and ``stack``
    (``self.formatException(record.exc_info)``).
    """

    def format(self, record: logging.LogRecord) -> str:
        """Return the JSON line for ``record``."""
        # TODO(milestone 1): build the dict described above. Helpers: _iso_utc(),
        #   _extra_fields(). Serialise with json.dumps(entry, default=str).
        raise NotImplementedError("TODO(milestone 1): JsonFormatter.format")


def _iso_utc(timestamp: float) -> str:
    """``1700000000.5`` -> ``"2023-11-14T22:13:20.500Z"``."""
    # TODO(milestone 1): datetime.fromtimestamp(..., tz=UTC).isoformat(timespec="milliseconds")
    #   and replace "+00:00" with "Z".
    raise NotImplementedError("TODO(milestone 1): _iso_utc")


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields a caller attached with ``extra=`` (attributes not in _RECORD_ATTRS)."""
    # TODO(milestone 1): filter vars(record); skip names starting with "_".
    raise NotImplementedError("TODO(milestone 1): _extra_fields")


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
    """True if ``value`` is 1-64 characters of letters, digits, ``.``, ``_`` or ``-``."""
    # TODO(milestone 2): use _REQUEST_ID.fullmatch.
    raise NotImplementedError("TODO(milestone 2): is_valid_request_id")


def resolve_request_id(incoming: str | None, id_factory: Callable[[], str] = new_request_id) -> str:
    """Reuse a valid incoming ID (so traces join up across services), else make one."""
    # TODO(milestone 2)
    raise NotImplementedError("TODO(milestone 2): resolve_request_id")


async def call_next_safely(call_next: CallNext, request: Request, logger: logging.Logger) -> Response:
    """Run the rest of the app; turn an unhandled exception into a logged 500 response.

    Log with ``logger.exception("unhandled error", extra=...)`` and return
    ``JSONResponse({"detail": "Internal Server Error", "request_id": ...}, status_code=500)``.
    """
    # TODO(milestone 2): try/except Exception around `await call_next(request)`.
    raise NotImplementedError("TODO(milestone 2): call_next_safely")


def route_template(request: Request) -> str:
    """The matched route's template (``/items/{item_id}``), or ``"unmatched"``.

    Labelling logs and metrics with the template keeps them groupable. Hint: after the
    app has handled the request, ``request.scope.get("route")`` is the matched route
    (it has a ``.path``), or ``None`` when nothing matched.
    """
    # TODO(milestone 2)
    raise NotImplementedError("TODO(milestone 2): route_template")


def log_request(
    logger: logging.Logger, request: Request, route: str, status: int, duration_seconds: float
) -> None:
    """Write the access-log line ``"request completed"`` for a finished request.

    Fields: method, path (URL path only - never the query string), route, status,
    duration_ms (rounded to 3 decimals). Level: ERROR for 5xx, WARNING for 4xx,
    INFO otherwise.
    """
    # TODO(milestone 2): logger.log(level, "request completed", extra={...})
    raise NotImplementedError("TODO(milestone 2): log_request")


# ---------------------------------------------------------------------------
# Milestones 3 and 4 - metrics in the Prometheus text format
# ---------------------------------------------------------------------------


def format_value(value: float) -> str:
    """Format a value like Prometheus clients: ``3`` -> ``"3.0"``, ``inf`` -> ``"+Inf"``.

    NaN -> ``"NaN"``, -inf -> ``"-Inf"``, everything else ``repr(float(value))``.
    """
    # TODO(milestone 3)
    raise NotImplementedError("TODO(milestone 3): format_value")


def escape_label_value(value: str) -> str:
    r"""Escape a label value: ``\`` -> ``\\``, ``"`` -> ``\"``, newline -> ``\n``."""
    # TODO(milestone 3): escape the backslash first - why?
    raise NotImplementedError("TODO(milestone 3): escape_label_value")


def _escape_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def _render_labels(names: Sequence[str], values: Sequence[str]) -> str:
    """``("method", "path"), ("GET", "/")`` -> ``{method="GET",path="/"}``; empty -> ``""``."""
    # TODO(milestone 3): escape each value with escape_label_value.
    raise NotImplementedError("TODO(milestone 3): _render_labels")


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
        # TODO(milestone 3): raise ValueError on missing/extra labels; return the values
        #   (as strings) in self.labelnames order.
        raise NotImplementedError("TODO(milestone 3): _Metric._key")

    def render(self) -> list[str]:
        """The ``# HELP`` and ``# TYPE`` lines followed by every sample line."""
        header = [f"# HELP {self.name} {_escape_help(self.help_text)}", f"# TYPE {self.name} {self.kind}"]
        with self._lock:
            return header + list(self._samples())

    def _samples(self) -> Iterator[str]:
        raise NotImplementedError


class Counter(_Metric):
    """A value that only goes up (requests served, errors seen)."""

    kind = "counter"

    def __init__(self, name: str, help_text: str, labelnames: Sequence[str] = ()) -> None:
        super().__init__(name, help_text, labelnames)
        self._values: dict[tuple[str, ...], float] = {}
        # TODO(milestone 3): an unlabelled counter should be exported as 0.0 from the start.

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        """Add ``amount`` (default 1) to the series identified by ``labels``."""
        # TODO(milestone 3): reject negative amounts; update under self._lock.
        raise NotImplementedError("TODO(milestone 3): Counter.inc")

    def value(self, **labels: str) -> float:
        """The current value of one series (0.0 if it was never incremented)."""
        raise NotImplementedError("TODO(milestone 3): Counter.value")

    def _samples(self) -> Iterator[str]:
        # TODO(milestone 3): one line per series, sorted by label values:
        #   name{label="value",...} 3.0
        raise NotImplementedError("TODO(milestone 3): Counter._samples")


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
        # TODO(milestone 4): reject an "le" label; require non-empty, strictly increasing
        #   buckets; append math.inf if missing; pre-create the series if unlabelled.
        self.buckets = tuple(float(b) for b in buckets)
        self._series: dict[tuple[str, ...], _Series] = {}

    def observe(self, value: float, **labels: str) -> None:
        """Record one observation in every bucket whose upper bound is >= ``value``."""
        # TODO(milestone 4): reject NaN; update bucket_counts, total and count.
        raise NotImplementedError("TODO(milestone 4): Histogram.observe")

    def _samples(self) -> Iterator[str]:
        # TODO(milestone 4): for each series (sorted): one _bucket line per bound with
        #   `le` as the LAST label, then _sum and _count lines.
        raise NotImplementedError("TODO(milestone 4): Histogram._samples")


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
        """Every metric, in registration order; every line ends with a newline."""
        # TODO(milestone 3)
        raise NotImplementedError("TODO(milestone 3): MetricsRegistry.render")


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
    """Count the request (status as a string label) and observe its latency."""
    # TODO(milestone 5)
    raise NotImplementedError("TODO(milestone 5): record_request")


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
        # TODO(milestone 2):
        #   1. request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER), id_factory)
        #   2. token = request_id_var.set(request_id)  - and reset(token) in a `finally:`
        #   3. start = clock(); response = await call_next_safely(call_next, request, log)
        #   4. duration = clock() - start; route = route_template(request)
        #   5. log_request(...); response.headers[REQUEST_ID_HEADER] = request_id
        # TODO(milestone 5): record_request(metrics, request.method, route, status, duration)
        return await call_next(request)

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
