"""Notes on SQLite: numbered SQL migrations, transactions and a repository layer behind a FastAPI app.

This is the notes resource from the ``rest-api`` project, now stored in a SQLite file so it survives
restarts. The domain models and the HTTP routes are given (you built them in rest-api); the database
layer is yours:

* Milestone 1: ``connect`` and ``transaction``.
* Milestone 2: ``discover_migrations``, ``applied_migrations``, ``schema_version``, ``apply_migrations``.
* Milestone 3: ``migrations/0002_create_tags.sql`` and ``migrations/0003_add_indexes.sql``.
* Milestone 4: ``SqliteNoteRepository``.
* Milestone 5: ``get_connection``, the startup migrations in ``create_app``, and ``app_from_env``.

Every function marked TODO raises ``NotImplementedError`` until you implement it. Run the tests with
``python -m pytest -k Milestone1`` (then 2, 3, ...). Run the API locally with::

    python -m uvicorn --factory notes_db:app_from_env --app-dir starter --reload
"""

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Protocol, Self, runtime_checkable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi import Path as PathParam
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Clock = Callable[[], datetime]
"""Returns the current time as a timezone-aware ``datetime``. Injected so tests control time."""


def utc_now() -> datetime:
    """The real clock: the current time in UTC."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Domain models (given: the same rules as the rest-api project)
# ---------------------------------------------------------------------------

TITLE_MAX = 200
BODY_MAX = 10_000
MAX_TAGS = 10
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def normalise_tags(tags: Sequence[str]) -> list[str]:
    """Strip and lower-case tags, drop duplicates (keeping first-seen order) and validate them.

    >>> normalise_tags([" Python", "python", "to-read"])
    ['python', 'to-read']
    """
    result: list[str] = []
    for raw in tags:
        tag = raw.strip().lower()
        if not TAG_PATTERN.fullmatch(tag):
            raise ValueError(
                f"invalid tag {raw!r}: use lowercase letters, digits and single hyphens, e.g. 'to-read'"
            )
        if tag not in result:
            result.append(tag)
    if len(result) > MAX_TAGS:
        raise ValueError(f"a note can have at most {MAX_TAGS} tags, got {len(result)}")
    return result


class NoteCreate(BaseModel):
    """The body of ``POST /notes``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=TITLE_MAX, examples=["Read about SQLite transactions"])
    body: str = Field(default="", max_length=BODY_MAX)
    tags: list[str] = Field(default_factory=list, examples=[["databases", "to-read"]])

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str]) -> list[str]:
        return normalise_tags(tags)


class NoteUpdate(BaseModel):
    """The body of ``PATCH /notes/{id}``: only the fields that are sent change."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    body: str | None = Field(default=None, max_length=BODY_MAX)
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else normalise_tags(tags)

    @model_validator(mode="after")
    def _check_sent_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one of: title, body, tags")
        for name in sorted(self.model_fields_set):
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null; leave it out to keep the current value")
        return self


class Note(BaseModel):
    """A stored note, as returned by the API. Frozen: change notes through the repository."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    body: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class Page(BaseModel):
    """One page of notes plus what a client needs to fetch the next one."""

    items: list[Note]
    total: int
    limit: int
    offset: int
    next_offset: int | None


class ErrorResponse(BaseModel):
    """The JSON body of 4xx errors raised with ``HTTPException``."""

    detail: str


def _to_text(moment: datetime) -> str:
    """Store a timestamp as ISO-8601 UTC text, e.g. ``2026-01-01T09:00:00.000000+00:00``."""
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware; the clock returned a naive datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _from_text(text: str) -> datetime:
    """Parse a timestamp written by ``_to_text``."""
    return datetime.fromisoformat(text)


# ---------------------------------------------------------------------------
# Milestone 1: connections and transactions
# ---------------------------------------------------------------------------


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a connection configured the same way everywhere in the app.

    * ``isolation_level=None``: autocommit mode. Python's ``sqlite3`` module does not open
      transactions behind your back; ``transaction()`` opens them explicitly.
    * ``check_same_thread=False``: FastAPI may create the connection in one worker thread and use it
      in another. That is safe because each request uses its connection serially and alone.
    * ``timeout=5``: wait up to 5 s for another writer's lock instead of failing at once.
    * ``row_factory=sqlite3.Row``: columns can be read by name (``row["title"]``).
    * ``PRAGMA foreign_keys = ON``: SQLite ignores ``REFERENCES`` constraints unless you ask, per connection.
    * ``PRAGMA journal_mode = WAL`` (file databases): readers do not block the writer, or vice versa.
    """
    # TODO(milestone 1): sqlite3.connect(...) with the three keyword arguments above, set row_factory,
    # run both PRAGMAs (skip WAL when path is ":memory:"), and return the connection.
    raise NotImplementedError("TODO(milestone 1): implement connect()")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the ``with`` block as one atomic write transaction.

    ``BEGIN IMMEDIATE`` takes the database's write lock up front, so two writers cannot both read and
    then fail when they try to upgrade to a write. Commits when the block finishes, rolls back (and
    re-raises) when it raises. Nesting is not supported: SQLite has one transaction per connection.
    """
    # TODO(milestone 1):
    #   1. If conn.in_transaction is already True, raise RuntimeError("transaction() cannot be nested ...").
    #   2. conn.execute("BEGIN IMMEDIATE")
    #   3. try: yield conn, then COMMIT.
    #      except BaseException: ROLLBACK (only if conn.in_transaction is still True), then `raise`.
    raise NotImplementedError("TODO(milestone 1): implement transaction()")
    yield conn  # unreachable for now; the `yield` makes this function a generator for @contextmanager


# ---------------------------------------------------------------------------
# Milestone 2: the migration runner
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9]+(?:_[a-z0-9]+)*)\.sql$")

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    checksum   TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(Exception):
    """A migration file is invalid, failed to apply, or disagrees with what the database recorded."""


@dataclass(frozen=True)
class Migration:
    """One numbered SQL file, e.g. ``0002_create_tags.sql`` -> version 2, name ``create_tags``."""

    version: int
    name: str
    sql: str
    checksum: str

    @property
    def filename(self) -> str:
        """The file name this migration was read from."""
        return f"{self.version:04d}_{self.name}.sql"


def checksum(sql: str) -> str:
    """SHA-256 of the migration text (newlines are already normalised by ``read_text``)."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Read every ``*.sql`` file in ``directory`` and return them sorted by version.

    Other files (a README, say) are ignored. Raises ``MigrationError`` for a ``.sql`` file that is
    not named ``NNNN_snake_case.sql``, for two files with the same number, and for gaps: versions must
    be exactly 1, 2, 3, ...
    """
    # TODO(milestone 2): loop over sorted(directory.glob("*.sql")); match each name with MIGRATION_FILE
    # (put the bad file name in the error message); collect Migration objects in a dict keyed by
    # version (duplicate -> MigrationError naming the number); then check the sorted versions are
    # exactly 1..n (gap -> MigrationError naming the missing number, e.g. "expected 0002").
    raise NotImplementedError("TODO(milestone 2): implement discover_migrations()")


def applied_migrations(conn: sqlite3.Connection) -> dict[int, str]:
    """Return ``{version: checksum}`` for every migration recorded in the database (creating the table)."""
    # TODO(milestone 2): execute SCHEMA_MIGRATIONS_DDL, then SELECT version, checksum ... ORDER BY version.
    raise NotImplementedError("TODO(milestone 2): implement applied_migrations()")


def schema_version(conn: sqlite3.Connection) -> int:
    """The highest applied migration number, or 0 for a database that has never been migrated."""
    # TODO(milestone 2): return 0 if sqlite_master has no table named schema_migrations; otherwise
    # SELECT COALESCE(MAX(version), 0) FROM schema_migrations.
    raise NotImplementedError("TODO(milestone 2): implement schema_version()")


def apply_migrations(
    conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR, clock: Clock = utc_now
) -> list[int]:
    """Apply every migration in ``directory`` that the database has not seen yet, in order.

    Returns the versions applied by this call (``[]`` when the schema is already current), so running
    it at every startup is safe. Checks the whole history before changing anything.
    """
    # TODO(milestone 2):
    #   1. Discover the files and read the applied {version: checksum}.
    #   2. Check the history FIRST: a recorded version with no file, or a file whose checksum differs
    #      from the recorded one ("... was edited after it was applied"), is a MigrationError.
    #   3. For each pending migration, apply it and its schema_migrations row atomically:
    #        conn.executescript("BEGIN IMMEDIATE;\n" + migration.sql)
    #        conn.execute("INSERT INTO schema_migrations (...) VALUES (?, ?, ?, ?)", (...))
    #        conn.execute("COMMIT")
    #      executescript() cannot take parameters and COMMITs any open transaction first, which is why
    #      the BEGIN is part of the script. On sqlite3.Error: ROLLBACK if conn.in_transaction, then raise
    #      MigrationError mentioning migration.filename (use `raise ... from exc`).
    raise NotImplementedError("TODO(milestone 2): implement apply_migrations()")


# ---------------------------------------------------------------------------
# Milestone 4: the repository
# ---------------------------------------------------------------------------


@runtime_checkable
class NoteRepository(Protocol):
    """What the API needs from storage. The rest-api project's in-memory store has the same shape."""

    def add(self, data: NoteCreate) -> Note:
        """Store a new note and return it with its id and timestamps."""
        ...

    def get(self, note_id: int) -> Note | None:
        """Return the note, or ``None`` if there is none with this id."""
        ...

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return ``(notes ordered by id, total matching)`` for one page, optionally filtered by tag."""
        ...

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Apply the fields that were sent; return the updated note, or ``None`` if it does not exist."""
        ...

    def delete(self, note_id: int) -> bool:
        """Delete the note; return whether it existed."""
        ...


SELECT_NOTE = "SELECT id, title, body, created_at, updated_at FROM notes WHERE id = ?"

# Given: a list of ids travels as ONE parameter (a JSON array, e.g. json.dumps([1, 2, 3])) that
# json_each() turns back into rows, so the SQL text stays fixed however many notes are on the page.
SELECT_TAGS = """
SELECT nt.note_id, t.name
FROM note_tags AS nt JOIN tags AS t ON t.id = nt.tag_id
WHERE nt.note_id IN (SELECT value FROM json_each(?))
ORDER BY nt.note_id, nt.position
"""

# TODO(milestone 4): write SELECT_PAGE and COUNT_PAGE. One fixed statement can serve both "all notes"
# and "notes with tag X":  WHERE ? IS NULL OR id IN (SELECT nt.note_id FROM note_tags ... WHERE t.name = ?)
# and pass the tag twice. Order by id, then LIMIT ? OFFSET ?.


class SqliteNoteRepository:
    """``NoteRepository`` backed by SQLite. Every statement is fixed SQL with ``?`` placeholders."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, data: NoteCreate) -> Note:
        """Insert the note and its tags in one transaction."""
        # TODO(milestone 4): inside `with transaction(self._conn):` INSERT the note (timestamps from
        # _to_text(self._clock())), take cursor.lastrowid, call self._set_tags(...). Then return
        # self._require(note_id). If _set_tags raises, the note row must be rolled back.
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository.add()")

    def get(self, note_id: int) -> Note | None:
        """Return the note with this id, or ``None``."""
        # TODO(milestone 4): SELECT_NOTE, then self._to_note(row, tags from self._tags_for([note_id])).
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository.get()")

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return one page of notes ordered by id and the total number of matching notes."""
        # TODO(milestone 4): raise ValueError unless limit >= 1 and offset >= 0 (SQLite treats a
        # negative LIMIT as "no limit"). Run SELECT_PAGE and COUNT_PAGE, fetch all tags for the page
        # with ONE call to self._tags_for(...), and build the notes.
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository.page()")

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Merge the sent fields into the stored note and write it back in one transaction."""
        # TODO(milestone 4): fields = changes.model_dump(exclude_unset=True). Inside one transaction:
        # read the current row (None -> return None), then
        #   UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?
        # with fields.get("title", current["title"]) etc. (a fixed column list, no dynamic SQL), and
        # call self._set_tags(...) only if "tags" in fields.
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository.update()")

    def delete(self, note_id: int) -> bool:
        """Delete the note; ``ON DELETE CASCADE`` removes its ``note_tags`` rows."""
        # TODO(milestone 4): DELETE ... WHERE id = ?; return cursor.rowcount == 1.
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository.delete()")

    def _set_tags(self, note_id: int, tags: Sequence[str]) -> None:
        """Replace the tags of ``note_id``. Runs inside the caller's transaction."""
        # TODO(milestone 4): delete the note's old note_tags rows; insert each tag name into `tags`
        # unless it exists (INSERT ... ON CONFLICT (name) DO NOTHING); insert the links with their
        # position: INSERT INTO note_tags (note_id, tag_id, position) SELECT ?, id, ? FROM tags WHERE name = ?
        # (executemany() runs one statement for a list of parameter tuples).
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository._set_tags()")

    def _tags_for(self, note_ids: Sequence[int]) -> dict[int, list[str]]:
        """Fetch the tags of many notes with one query: ``{note_id: [tag, ...]}`` in stored order."""
        # TODO(milestone 4): return {} for no ids; otherwise run SELECT_TAGS with the single parameter
        # (json.dumps(list(note_ids)),) and group the (note_id, name) rows into lists.
        raise NotImplementedError("TODO(milestone 4): implement SqliteNoteRepository._tags_for()")

    def _require(self, note_id: int) -> Note:
        note = self.get(note_id)
        if note is None:
            raise LookupError(f"note {note_id} disappeared right after it was written")
        return note

    @staticmethod
    def _to_note(row: sqlite3.Row, tags: list[str]) -> Note:
        return Note(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            tags=tags,
            created_at=_from_text(row["created_at"]),
            updated_at=_from_text(row["updated_at"]),
        )


# ---------------------------------------------------------------------------
# Milestone 5: the HTTP API (the routes are given; the database wiring is yours)
# ---------------------------------------------------------------------------


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request, always closed afterwards (even when the handler raises)."""
    # TODO(milestone 5): conn = connect(request.app.state.db_path); try: yield conn; finally: conn.close()
    raise NotImplementedError("TODO(milestone 5): implement get_connection()")
    yield  # unreachable for now; the `yield` makes this a generator (a FastAPI "yield dependency")


def get_repository(
    request: Request, conn: Annotated[sqlite3.Connection, Depends(get_connection)]
) -> NoteRepository:
    """The repository for this request, bound to this request's connection."""
    return SqliteNoteRepository(conn, request.app.state.clock)


Repo = Annotated[NoteRepository, Depends(get_repository)]
NoteId = Annotated[int, PathParam(ge=1, description="The note's id")]
NOT_FOUND = {404: {"model": ErrorResponse, "description": "There is no note with this id"}}


def _not_found(note_id: int) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"note {note_id} not found")


def notes_router() -> APIRouter:
    """The ``/notes`` routes. Built by a function so every app gets its own router."""
    router = APIRouter(prefix="/notes", tags=["notes"])

    @router.post("", status_code=status.HTTP_201_CREATED, summary="Create a note")
    def create_note(data: NoteCreate, repo: Repo, request: Request, response: Response) -> Note:
        note = repo.add(data)
        response.headers["Location"] = str(request.url_for("get_note", note_id=note.id))
        return note

    @router.get("", summary="List notes, a page at a time")
    def list_notes(
        repo: Repo,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
        offset: Annotated[int, Query(ge=0)] = 0,
        tag: Annotated[str | None, Query(max_length=50, description="Only notes with this tag")] = None,
    ) -> Page:
        wanted = tag.strip().lower() if tag else None
        items, total = repo.page(offset=offset, limit=limit, tag=wanted)
        next_offset = offset + limit if offset + limit < total else None
        return Page(items=items, total=total, limit=limit, offset=offset, next_offset=next_offset)

    @router.get("/{note_id}", summary="Get one note", responses=NOT_FOUND)
    def get_note(note_id: NoteId, repo: Repo) -> Note:
        note = repo.get(note_id)
        if note is None:
            raise _not_found(note_id)
        return note

    @router.patch("/{note_id}", summary="Change some fields of a note", responses=NOT_FOUND)
    def update_note(note_id: NoteId, changes: NoteUpdate, repo: Repo) -> Note:
        note = repo.update(note_id, changes)
        if note is None:
            raise _not_found(note_id)
        return note

    @router.delete(
        "/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note", responses=NOT_FOUND
    )
    def delete_note(note_id: NoteId, repo: Repo) -> Response:
        if not repo.delete(note_id):
            raise _not_found(note_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _operation_id(route: APIRoute) -> str:
    """Use the function name (``create_note``) as the OpenAPI operationId."""
    return route.name


def create_app(db_path: Path | str, clock: Clock = utc_now) -> FastAPI:
    """Build the API for the SQLite file at ``db_path``. Pending migrations are applied at startup."""
    path = Path(db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # TODO(milestone 5): before the app starts serving, open a connection with connect(path),
        # call apply_migrations(conn, clock=clock), and close the connection (in a `finally`).
        raise NotImplementedError("TODO(milestone 5): apply the migrations at startup")
        yield  # unreachable for now

    app = FastAPI(
        title="Notes API (SQLite)",
        version="1.0.0",
        description="The notes resource from the rest-api project, persisted in SQLite.",
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.db_path = path
    app.state.clock = clock
    app.include_router(notes_router())
    return app


def app_from_env() -> FastAPI:
    """uvicorn factory: the database file comes from ``NOTES_DB_PATH`` (default ``notes.db``)."""
    # TODO(milestone 5): read NOTES_DB_PATH with os.environ.get(..., "notes.db") and call create_app.
    raise NotImplementedError("TODO(milestone 5): implement app_from_env()")
