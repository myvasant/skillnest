# Notes & Bookmarks REST API

Build a small but properly designed REST API with FastAPI and Pydantic:

* **Resources and status codes**: `/notes` and `/bookmarks`, with 201 + `Location` on create, 404 for
  missing items, 204 on delete, 405 for unsupported methods, 409 for duplicates and 422 for invalid input.
* **Validation with Pydantic**: length limits, stripped strings, normalised tags, http(s)-only URLs, and
  request models that reject unknown fields (so clients cannot choose their own `id`).
* **Pagination**: `?limit=&offset=` with a `total` and a `next_offset` to follow.
* **A repository interface**: routes depend on `NoteRepository`, not on a dictionary. The in-memory
  implementation here is swapped for SQLite in the `crud-database-app` project.
* **OpenAPI docs**: summaries, tags, documented error responses and clean operation ids, browsable at `/docs`.

```text
POST   /notes            {"title": "Groceries", "tags": ["Home"]}  -> 201, Location: /notes/1
GET    /notes?limit=2                                              -> 200 {"items": [...], "total": 3, "limit": 2, "offset": 0, "next_offset": 2}
GET    /notes/1                                                    -> 200 {"id": 1, "title": "Groceries", "tags": ["home"], ...}
PATCH  /notes/1          {"body": "eggs, milk"}                    -> 200 (only body changes)
DELETE /notes/1                                                    -> 204 (no body)
GET    /notes/1                                                    -> 404 {"detail": "note 1 not found"}
POST   /bookmarks        {"url": "https://Example.com", "title": "Example"}  -> 201 {"url": "https://example.com/", ...}
POST   /bookmarks        {"url": "https://example.com/", "title": "Again"}   -> 409
```

## Setup

You need Python 3.11 or newer.

Windows PowerShell:

```powershell
cd projects\rest-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/rest-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                 # all milestones, against starter/ (your code)
python -m pytest -k Milestone1   # one milestone at a time
python -m pytest -x              # stop at the first failure
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

The tests use FastAPI's `TestClient` (no server, no network) and a `FakeClock`, so timestamps such as
`2026-01-15T09:30:00Z` are exact and the suite is deterministic.

## Running the API

```bash
python -m uvicorn --factory notes_api:create_app --app-dir starter --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive Swagger UI (or `/redoc`, or the raw `/openapi.json`).
Data lives in memory, so it disappears when the server restarts. Use `--app-dir solution` to try the
reference version.

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1Models` | `normalise_tags`, constraints on `NoteCreate` / `NoteUpdate` / `BookmarkCreate`, immutable `Note` / `Bookmark` |
| 2 | `TestMilestone2Repository` | `InMemoryNoteRepository`: ids, clock timestamps, partial updates, delete, paging |
| 3 | `TestMilestone3Endpoints` | `POST/GET/PATCH/DELETE /notes`: 201 + Location, 404, 204, 405, 422 |
| 4 | `TestMilestone4Pagination` | `next_offset`, `GET /notes?limit=&offset=&tag=` with bounds checks |
| 5 | `TestMilestone5BookmarksAndDocs` | `/bookmarks` (409 on duplicates) and OpenAPI: summaries, tags, error models, operation ids |

## Layout

```text
rest-api/
  README.md
  requirements.txt
  conftest.py              # GW_TARGET=solution switches the tests to the reference solution
  starter/notes_api.py     # your code: TODOs, and functions that raise NotImplementedError
  solution/notes_api.py    # reference solution
  tests/test_notes_api.py
```

## Optional extras

* Try the API from the command line with `curl` or the built-in Swagger UI; no extra packages are needed.
* Generate a typed client from `/openapi.json` with a tool such as `openapi-python-client` (optional,
  `python -m pip install openapi-python-client`). Clean operation ids give clean method names.
* Next steps: persist the same notes in SQLite in `crud-database-app`, then put a cache in front of a
  slow endpoint in `caching-demo`.
