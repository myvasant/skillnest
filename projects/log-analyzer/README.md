# Log analyzer (starter kit)

A command-line tool that reads a web-server access log **as a stream**, parses every line with a
regular expression, and reports status codes, top paths and the error rate per hour. It never loads
the whole file into memory, and a broken line is counted, not fatal. Standard library only.

## The problem

Your team's web server writes one line per request in the Common or Combined Log Format:

```text
203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"
198.51.100.23 - alice [22/Oct/2026:13:18:10 +0000] "GET /api/orders?page=2 HTTP/1.1" 500 87
```

That is: client IP, identity, user, `[timestamp]`, `"METHOD path protocol"`, status code, response
size in bytes (`-` for none) and, in the Combined format, `"referrer" "user agent"`.

After an incident someone always asks the same questions: *How many requests failed? Which pages
are hit most? When did the errors start?* The log can be gigabytes, contains lines that do not
follow the format (truncated writes, attack probes, binary garbage), and is written by clients you
do not control. The tool must:

* parse each line into a typed, immutable record, rejecting malformed lines with a reason;
* process the file lazily with generators, so memory use does not grow with the file size;
* count status codes and classes (`2xx` … `5xx`), the top N paths (query strings removed, ties
  broken alphabetically) and the error rate per UTC hour, with a configurable error threshold
  (`>= 500` by default, `>= 400` to include client errors);
* optionally restrict the analysis to a time window (`--since`, `--until`);
* print a text report or JSON, and show malformed lines safely (escaped) on request.

## What's in this folder

| Path | Purpose |
|---|---|
| `starter/log_analyzer.py` | Your file: dataclasses are given; every function has a docstring and TODOs and raises `NotImplementedError`. |
| `solution/log_analyzer.py` | The reference solution. Try the milestones yourself first. |
| `tests/test_log_analyzer.py` | 65 behaviour tests, one class per milestone. |
| `conftest.py` | Makes the tests import `starter/` (default) or `solution/` (`GW_TARGET=solution`). |
| `requirements.txt` | Only `pytest`; the tool itself needs nothing beyond Python 3.11+. |

## Setup

Run these commands from inside this folder (`projects/log-analyzer`).

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
once, or skip activation and call `.\.venv\Scripts\python.exe` directly.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                    # all tests, against starter/ (they fail until you implement it)
python -m pytest -k Milestone1      # just one milestone
python -m pytest -k Milestone2 -x   # stop at the first failure
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest
Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

The tests write their log files into pytest's `tmp_path`, use fixed timestamps, and call `main([...])`
in-process with `capsys`, so they are fast and never depend on the clock or on files of yours.

## Running the program

Create a small sample log first.

Windows (PowerShell):

```powershell
@'
203.0.113.7 - - [22/Oct/2026:13:05:01 +0000] "GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"
203.0.113.7 - - [22/Oct/2026:13:05:02 +0000] "GET /style.css HTTP/1.1" 304 - "https://example.org/" "Mozilla/5.0"
198.51.100.23 - alice [22/Oct/2026:13:17:45 +0000] "POST /api/orders HTTP/1.1" 201 512
198.51.100.23 - alice [22/Oct/2026:13:18:10 +0000] "GET /api/orders?page=2 HTTP/1.1" 500 87
this line is not a log entry
192.0.2.44 - - [22/Oct/2026:13:59:59 +0000] "GET /index.html HTTP/1.1" 200 2326
192.0.2.44 - - [22/Oct/2026:14:00:00 +0000] "GET /missing HTTP/1.1" 404 153
203.0.113.9 - - [22/Oct/2026:16:30:00 +0200] "GET /index.html HTTP/2.0" 200 2326 "-" "curl/8.5.0"
203.0.113.9 - - [22/Oct/2026:14:31:00 +0000] "GET /api/orders HTTP/1.1" 503 0
2001:db8::1 - - [22/Oct/2026:14:45:12 +0000] "DELETE /api/orders/7 HTTP/1.1" 204 -
'@ | Set-Content -Path access.log -Encoding utf8
```

macOS / Linux: save the same lines with `cat > access.log` (paste, then press Ctrl+D).

Windows PowerShell 5.1 writes UTF-8 files with a byte-order mark (BOM); `read_lines` opens files
with `encoding="utf-8-sig"`, which accepts UTF-8 with or without one.

```text
> python solution/log_analyzer.py access.log --top 3 --show-malformed
Access log report
=================
Requests:        9
Malformed lines: 1
Bytes sent:      7,730
Error rate:      22.2% (status >= 500)

Status codes:
  200         3
  201         1
  204         1
  304         1
  404         1
  500         1
  503         1

Status classes:
  2xx         5
  3xx         1
  4xx         1
  5xx         2

Top 3 paths:
  /api/orders  3
  /index.html  3
  /api/orders/7  1

Errors per hour (UTC):
  2026-10-22 13:00       5 requests      1 errors   20.0%
  2026-10-22 14:00       4 requests      1 errors   25.0%

Malformed lines (first 1):
  line 5: line does not match the access-log format (Common or Combined): this line is not a log entry
> python solution/log_analyzer.py access.log --json --since 2026-10-22T14:00 --error-threshold 400
{ "requests": 4, "malformed": 1, "error_threshold": 400, "error_rate": 0.5, ... }
> python solution/log_analyzer.py nope.log
error: cannot read nope.log: No such file or directory
```

Note the request logged at `16:30:00 +0200`: it is 14:30 UTC, so it lands in the 14:00 bucket.
`-` instead of a file name reads standard input: `Get-Content access.log | python solution/log_analyzer.py -`
(PowerShell) or `python solution/log_analyzer.py - < access.log` (macOS/Linux).

Replace `solution/` with `starter/` to run your own version.

### Report format

The text report has exactly these sections (the tests ignore how many spaces separate columns):

```text
Access log report
=================
Requests:        <count>
Malformed lines: <count>
Bytes sent:      <count with thousands separators>
Error rate:      <percent with 1 decimal>% (status >= <threshold>)

Status codes:              one line per code, ascending: "  <code>  <count>"
Status classes:            "  2xx  <count>" ... in class order
Top <N> paths:             "  <path>  <count>", most requested first, ties alphabetical
Errors per hour (UTC):     "  YYYY-MM-DD HH:00  <n> requests  <n> errors  <rate>%"
```

With no valid requests, the four sections are replaced by a blank line and `No requests to report.`.
With `--show-malformed`, a final section `Malformed lines (first N):` lists
`  line <number>: <reason>: <escaped excerpt>`.

`--json` prints an object with the keys `requests`, `malformed`, `bytes_sent`, `error_threshold`,
`error_rate` (a fraction rounded to 4 decimals), `status_counts` (string keys), `status_classes`,
`top_paths` (`[{"path", "count"}]`), `hourly` (`[{"hour" (ISO 8601, UTC), "requests", "errors",
"error_rate"}]`) and `malformed_examples` (`[{"line", "reason"}]`, without the raw text).

## Milestones

1. **Parse one line** (`-k Milestone1`): write the `LOG_LINE` regex with named groups and
   `parse_line` / `parse_timestamp`. Return an immutable `LogRecord` with an aware `datetime`;
   raise `LogParseError` (a `ValueError`) whose `reason` mentions *format*, *timestamp* or *status*.
2. **Stream** (`-k Milestone2`): `read_lines` (a generator that opens the file lazily and survives
   bad bytes and a BOM), `parse_records` (skips blank lines, reports malformed ones with line
   numbers through a callback, never reads ahead) and `filter_records` (time window, validated
   eagerly).
3. **Aggregate** (`-k Milestone3`): `strip_query`, `status_class`, `hour_bucket` and the `LogStats`
   accumulator (`add`, `add_malformed` with a bounded list of examples, `error_rate`,
   `status_classes`, `top_paths`, `hourly_error_rates`), then `analyze`, which wires the whole
   pipeline together in one pass.
4. **Report and CLI** (`-k Milestone4`): `safe_excerpt`, `format_report`, `report_to_dict`, the
   argparse types `parse_cli_datetime` and `positive_int`, `build_parser` and `main`.

## Security notes

* **Every log line is attacker-controlled.** Paths, user agents and referrers are whatever the
  client sent. Never `eval` them, never build shell commands or SQL from them, and print them only
  through `safe_excerpt`, which escapes terminal control characters (an `ESC [2J` in a user agent
  could otherwise clear or rewrite a colleague's terminal).
* **Regular expressions can be attacked too (ReDoS).** Nested quantifiers such as `(a+)+` or `.*`
  followed by more `.*` can take exponential time on crafted input. The pattern here uses negated
  character classes with fixed delimiters, so matching stays linear in the line length.
* **Logs contain personal data.** IP addresses and user names are personal data in many
  jurisdictions (for example under the GDPR). The report aggregates instead of listing them, the
  JSON output omits the raw malformed lines, and you should not share raw logs more widely than
  necessary.
* **Huge or hostile files.** Streaming keeps memory flat, query strings are stripped so random
  `?x=...` values cannot blow up the path table, and only the first 20 malformed examples are kept.
