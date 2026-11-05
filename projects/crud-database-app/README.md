# CRUD database app: notes on SQLite

The notes API from the `rest-api` project kept everything in a Python dictionary, so every restart
wiped it. In this project the same API stores its notes in a **SQLite** file. You build the layer
that real backends rely on:

* **Connections and transactions**: one connection per request, explicit `BEGIN IMMEDIATE` /
  `COMMIT` / `ROLLBACK`, foreign keys switched on.
* **Schema migrations**: numbered SQL files (`0001_create_notes.sql`, `0002_create_tags.sql`, ...)
  applied once each, in order, and recorded in a `schema_migrations` table, so every copy of the
  database can be brought up to date safely.
* **A repository layer**: `SqliteNoteRepository` hides the SQL behind the same methods the in-memory
  store had (`add`, `get`, `page`, `update`, `delete`). Every query uses `?` placeholders.
* **The API on top**: the same endpoints and status codes as `rest-api`, now surviving restarts.

```text
POST   /notes {"title": "Read about WAL", "tags": ["databases"]}  -> 201, Location: /notes/1
GET    /notes?limit=20&offset=0&tag=databases                     -> 200 {"items": [...], "total": 1, "next_offset": null, ...}
PATCH  /notes/1 {"body": "Readers do not block writers"}          -> 200
DELETE /notes/1                                                   -> 204
(stop the server, start it again)
GET    /notes/1                                                   -> 404 (it was deleted), but every other note is still there
```

SQLite comes with Python (`import sqlite3`); there is no server to install.

## Setup

Windows PowerShell:

```powershell
cd projects\crud-database-app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/crud-database-app
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                 # all milestones, against starter/ (your code)
python -m pytest -k Milestone1   # one milestone at a time
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

Every test creates its own database file under pytest's `tmp_path`, so tests never share data and
never touch a `notes.db` you created yourself.

## Running the API

```powershell
$env:NOTES_DB_PATH = "notes.db"
python -m uvicorn --factory notes_db:app_from_env --app-dir starter --reload
```

```bash
NOTES_DB_PATH=notes.db python -m uvicorn --factory notes_db:app_from_env --app-dir starter --reload
```

Open <http://127.0.0.1:8000/docs>, create a few notes, stop the server (Ctrl+C), start it again and
list them: they are still there. Use `--app-dir solution` to run the reference solution.

## Looking inside the database

Python 3.12 and newer include a SQLite shell (`python -m sqlite3`); on 3.11 install the `sqlite3`
command-line tool instead.

```text
python -m sqlite3 notes.db
sqlite> .tables
note_tags          notes              schema_migrations  tags
sqlite> SELECT version, name, applied_at FROM schema_migrations;
sqlite> SELECT n.id, n.title, t.name FROM notes n JOIN note_tags nt ON nt.note_id = n.id JOIN tags t ON t.id = nt.tag_id;
sqlite> EXPLAIN QUERY PLAN SELECT note_id FROM note_tags WHERE tag_id = 1;
```

## Milestones

| # | Tests | What you build |
|---|-------|----------------|
| 1 | `TestMilestone1ConnectionAndTransactions` | `connect()` (autocommit mode, `Row` factory, foreign keys, WAL) and the `transaction()` context manager |
| 2 | `TestMilestone2MigrationRunner` | `discover_migrations`, `applied_migrations`, `schema_version`, `apply_migrations`: ordered, atomic, idempotent, tamper-evident |
| 3 | `TestMilestone3Schema` | `migrations/0002_create_tags.sql` and `migrations/0003_add_indexes.sql` |
| 4 | `TestMilestone4Repository` | `SqliteNoteRepository`: CRUD, tags, pagination, all-or-nothing writes, injection-safe queries |
| 5 | `TestMilestone5Api` | `get_connection` (one connection per request), migrations at startup, `app_from_env` |

The domain models (`NoteCreate`, `NoteUpdate`, `Note`, `Page`) and the route functions are given:
they are the ones you wrote in `rest-api`. This project is about what happens underneath them.

## Rules the migration runner enforces

* Files are named `NNNN_snake_case_name.sql` and numbered 1, 2, 3, ... without gaps or duplicates.
* Each file runs **inside one transaction together with its `schema_migrations` row**: if any
  statement fails, nothing from that file remains and it is not recorded. (SQLite can roll back
  `CREATE TABLE`; MySQL, for example, cannot.)
* A file is never run twice. Running `apply_migrations` on every startup is therefore safe.
* **Never edit a migration that has been applied anywhere.** The runner stores each file's SHA-256
  checksum and refuses to continue if an applied file changed; add a new numbered file instead.
* Migration files must not contain `BEGIN` or `COMMIT`; the runner owns the transaction.

## Layout

```text
crud-database-app/
  README.md
  requirements.txt
  conftest.py                     # GW_TARGET=solution switches the tests to the reference solution
  starter/notes_db.py             # your code: TODO functions raise NotImplementedError
  starter/migrations/0001_create_notes.sql   # complete: the worked example
  starter/migrations/0002_create_tags.sql    # TODO (milestone 3)
  starter/migrations/0003_add_indexes.sql    # TODO (milestone 3)
  solution/notes_db.py            # reference solution
  solution/migrations/*.sql
  tests/test_notes_db.py
```

## Optional: the same app on PostgreSQL

This step is **optional**: the tests and the solution use only SQLite. Do it once the SQLite version
passes, to see which parts of your design carry over to a client-server database.

1. Run a local PostgreSQL server: install it from <https://www.postgresql.org/download/>, or with
   Docker:
   `docker run --name notes-pg -e POSTGRES_PASSWORD=devpassword -p 5432:5432 -d postgres:17`
   (a throwaway password for a local container only; never reuse it).
2. Install the driver into your venv: `python -m pip install "psycopg[binary]>=3.2"`.
3. Connect with `psycopg.connect("postgresql://postgres:devpassword@localhost:5432/postgres")`.
   Read the connection string from an environment variable, never from the code.
4. Port the differences:

| SQLite (this project) | PostgreSQL with psycopg 3 |
|---|---|
| `?` placeholders | `%s` (or `%(name)s`) placeholders, still never string formatting |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` |
| `cursor.lastrowid` | `INSERT ... RETURNING id` |
| `transaction()` with `BEGIN IMMEDIATE` | `with conn.transaction():` |
| ISO-8601 `TEXT` timestamps | `TIMESTAMPTZ` columns (psycopg returns aware `datetime`s) |
| `json_each(?)` for a list of ids | `WHERE id = ANY(%s)` with a Python list |
| `PRAGMA foreign_keys = ON` | not needed: foreign keys are always enforced |
| `executescript()` for a migration file | `cursor.execute(file_text)` inside `conn.transaction()` (PostgreSQL DDL is transactional too) |

Keep the `NoteRepository` interface unchanged and write a `PostgresNoteRepository` beside the SQLite
one: the API code should not need to change. Use a connection pool (`psycopg_pool`) instead of one
new connection per request once you serve real traffic.
