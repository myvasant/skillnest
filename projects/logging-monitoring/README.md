# Logging and monitoring: JSON logs, request IDs and Prometheus metrics

A customer reports "the app was slow at about 14:05 and then showed an error". With
`print()`-style logs you would grep through thousands of interleaved lines from
concurrent requests and still not know which ones belonged together, or whether the
whole service was slow or just one endpoint.

In this project you instrument a small FastAPI service the way production services are
instrumented:

* **Structured logs** - one JSON object per line, with a request ID on every line.
* **Request IDs** - accepted from `X-Request-ID` when safe, generated otherwise, stored in
  a `ContextVar`, echoed in the response.
* **Metrics** - `GET /metrics` exposes a request counter and a latency histogram in the
  Prometheus text format, written by hand (no client library), labelled by route
  template so cardinality stays bounded.

Example:

```text
$ curl -i -H "X-Request-ID: demo-1" http://127.0.0.1:8000/items/1
HTTP/1.1 200 OK
x-request-id: demo-1
{"id":1,"name":"keyboard"}

stderr:
{"ts": "2026-10-22T14:05:01.123Z", "level": "INFO", "logger": "observability_app", "message": "item looked up", "request_id": "demo-1", "item_id": 1, "found": true}
{"ts": "2026-10-22T14:05:01.124Z", "level": "INFO", "logger": "observability_app", "message": "request completed", "request_id": "demo-1", "method": "GET", "path": "/items/1", "route": "/items/{item_id}", "status": 200, "duration_ms": 1.402}

$ curl http://127.0.0.1:8000/metrics
# HELP http_requests_total HTTP requests handled, by method, route template and status code.
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/items/{item_id}",status="200"} 1.0
# HELP http_request_duration_seconds Time spent handling HTTP requests, in seconds.
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",path="/items/{item_id}",le="0.005"} 1.0
...
http_request_duration_seconds_bucket{method="GET",path="/items/{item_id}",le="+Inf"} 1.0
http_request_duration_seconds_sum{method="GET",path="/items/{item_id}"} 0.001402
http_request_duration_seconds_count{method="GET",path="/items/{item_id}"} 1.0
```

## Setup

Windows (PowerShell):

```powershell
cd projects/logging-monitoring
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/logging-monitoring
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the service (from the kit folder):

```bash
python -m uvicorn --app-dir starter --factory observability_app:create_app --port 8000
```

Use `--app-dir solution` to run the reference.

## Running the tests

```powershell
python -m pytest                  # everything, against starter/
python -m pytest -k Milestone1    # one milestone
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
python -m pytest
python -m pytest -k Milestone1
GW_TARGET=solution python -m pytest
```

The tests are deterministic: request durations come from an injected fake clock (every
request takes exactly 0.25 s), request IDs from a counter, and logs are captured in an
in-memory stream.

## Milestones

1. **JSON logs** (`TestMilestone1JsonLogs`) - `JsonFormatter.format`: `ts`, `level`,
   `logger`, `message`, `request_id`, `extra=` fields, structured exceptions, one line per
   entry even for hostile messages.
2. **Request IDs and access logs** (`TestMilestone2RequestIds`) - validate/resolve IDs,
   write the middleware in `create_app`, `route_template`, one `request completed` line
   per request (level by status), and a logged 500 for unhandled exceptions.
3. **Counters** (`TestMilestone3Counters`) - `format_value`, label escaping, `Counter`
   and `MetricsRegistry.render` producing exact Prometheus text.
4. **Histograms** (`TestMilestone4Histograms`) - cumulative `le` buckets ending in
   `+Inf`, `_sum`, `_count`, bucket validation.
5. **The /metrics endpoint** (`TestMilestone5MetricsEndpoint`) - `record_request` in the
   middleware, labels from route templates (`/items/{item_id}`, `unmatched`), latency from
   the injected clock, and a well-formed exposition.

## Optional: scrape it with Prometheus

Not needed for the tests. If you have Docker, run Prometheus with a scrape config that
targets `host.docker.internal:8000` (Windows/macOS) and open `http://localhost:9090` to
query `rate(http_requests_total[1m])` or
`histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`.

## Layout

```
logging-monitoring/
  conftest.py                     selects starter/ or solution/
  requirements.txt                fastapi, uvicorn, httpx, pytest
  starter/observability_app.py    your code (TODOs per milestone)
  solution/observability_app.py   reference solution
  tests/test_observability_app.py tests, one class per milestone
```
