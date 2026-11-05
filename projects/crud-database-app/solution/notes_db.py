"""Notes on SQLite: numbered SQL migrations, transactions and a repository layer behind a FastAPI app.

This is the notes resource from the ``rest-api`` project, now stored in a SQLite file so it survives
restarts:

* ``connect`` / ``transaction``: connection settings and explicit ``BEGIN IMMEDIATE``/``COMMIT``/``ROLLBACK``.
* ``discover_migrations`` / ``apply_migrations``: ``NNNN_name.sql`` files applied once each, in order.
* ``SqliteNoteRepository``: create, read, update, delete and paginate with parameterised queries only.
* ``create_app``: the HTTP API. Migrations run at startup; every request gets its own connection.

Run it locally::

    python -m uvicorn --factory notes_db:app_from_env --app-dir solution --reload
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
# Domain models (the same rules as the rest-api project)
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
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the ``with`` block as one atomic write transaction.

    ``BEGIN IMMEDIATE`` takes the database's write lock up front, so two writers cannot both read and
    then fail when they try to upgrade to a write. Commits when the block finishes, rolls back (and
    re-raises) when it raises. Nesting is not supported: SQLite has one transaction per connection.
    """
    if conn.in_transaction:
        raise RuntimeError("transaction() cannot be nested: this connection already has an open transaction")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:  # some errors make SQLite roll back by itself
            conn.execute("ROLLBACK")
        raise


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
    found: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_FILE.fullmatch(path.name)
        if match is None:
            raise MigrationError(
                f"bad migration file name {path.name!r}: "
                "expected NNNN_snake_case_name.sql, e.g. 0004_add_pinned.sql"
            )
        version = int(match.group(1))
        if version in found:
            raise MigrationError(
                f"two migrations share number {version:04d}: {found[version].filename} and {path.name}"
            )
        sql = path.read_text(encoding="utf-8")
        found[version] = Migration(version=version, name=match.group(2), sql=sql, checksum=checksum(sql))
    ordered = [found[version] for version in sorted(found)]
    for expected, migration in enumerate(ordered, start=1):
        if migration.version != expected:
            raise MigrationError(
                f"migration numbers must run 1, 2, 3, ... without gaps: expected {expected:04d}, "
                f"found {migration.filename}"
            )
    return ordered


def applied_migrations(conn: sqlite3.Connection) -> dict[int, str]:
    """Return ``{version: checksum}`` for every migration recorded in the database (creating the table)."""
    conn.execute(SCHEMA_MIGRATIONS_DDL)
    rows = conn.execute("SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
    return {row[0]: row[1] for row in rows}


def schema_version(conn: sqlite3.Connection) -> int:
    """The highest applied migration number, or 0 for a database that has never been migrated."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if exists is None:
        return 0
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]


def _check_history(migrations: Sequence[Migration], applied: dict[int, str]) -> None:
    """Refuse to continue if the database and the migration files disagree about the past."""
    known = {migration.version: migration for migration in migrations}
    unknown = sorted(set(applied) - set(known))
    if unknown:
        raise MigrationError(
            f"the database has migrations {unknown} that are not in the migrations folder; "
            "is this code older than the database?"
        )
    for version, recorded in applied.items():
        if known[version].checksum != recorded:
            raise MigrationError(
                f"migration {known[version].filename} was edited after it was applied; "
                "never change an applied migration, add a new one instead"
            )


def _apply_one(conn: sqlite3.Connection, migration: Migration, clock: Clock) -> None:
    """Apply one migration and record it, atomically: either both happen or neither does."""
    try:
        # executescript() cannot take parameters and, in Python's default (legacy) transaction mode,
        # COMMITs any open transaction first, so the BEGIN has to be part of the script itself.
        # Migration files are trusted code shipped with the app, never user input.
        conn.executescript("BEGIN IMMEDIATE;\n" + migration.sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            (migration.version, migration.name, migration.checksum, _to_text(clock())),
        )
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise MigrationError(f"migration {migration.filename} failed and was rolled back: {exc}") from exc


def apply_migrations(
    conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR, clock: Clock = utc_now
) -> list[int]:
    """Apply every migration in ``directory`` that the database has not seen yet, in order.

    Returns the versions applied by this call (``[]`` when the schema is already current), so running
    it at every startup is safe. Checks the whole history before changing anything.
    """
    if conn.in_transaction:
        raise MigrationError("apply_migrations() needs a connection with no open transaction")
    migrations = discover_migrations(directory)
    applied = applied_migrations(conn)
    _check_history(migrations, applied)
    newly_applied: list[int] = []
    for migration in migrations:
        if migration.version not in applied:
            _apply_one(conn, migration, clock)
            newly_applied.append(migration.version)
    return newly_applied


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

SELECT_PAGE = """
SELECT id, title, body, created_at, updated_at
FROM notes
WHERE ? IS NULL OR id IN (
    SELECT nt.note_id FROM note_tags AS nt JOIN tags AS t ON t.id = nt.tag_id WHERE t.name = ?
)
ORDER BY id
LIMIT ? OFFSET ?
"""

COUNT_PAGE = """
SELECT COUNT(*)
FROM notes
WHERE ? IS NULL OR id IN (
    SELECT nt.note_id FROM note_tags AS nt JOIN tags AS t ON t.id = nt.tag_id WHERE t.name = ?
)
"""

# A list of ids travels as ONE parameter (a JSON array) that json_each() turns back into rows, so the
# SQL text stays fixed however many notes are on the page.
SELECT_TAGS = """
SELECT nt.note_id, t.name
FROM note_tags AS nt JOIN tags AS t ON t.id = nt.tag_id
WHERE nt.note_id IN (SELECT value FROM json_each(?))
ORDER BY nt.note_id, nt.position
"""


class SqliteNoteRepository:
    """``NoteRepository`` backed by SQLite. Every statement is fixed SQL with ``?`` placeholders."""

    def __init__(self, conn: sqlite3.Connection, clock: Clock = utc_now) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, data: NoteCreate) -> Note:
        """Insert the note and its tags in one transaction."""
        now = _to_text(self._clock())
        with transaction(self._conn):
            cursor = self._conn.execute(
                "INSERT INTO notes (title, body, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (data.title, data.body, now, now),
            )
            note_id = cursor.lastrowid
            assert note_id is not None  # always set after a successful INSERT
            self._set_tags(note_id, data.tags)
        return self._require(note_id)

    def get(self, note_id: int) -> Note | None:
        """Return the note with this id, or ``None``."""
        row = self._conn.execute(SELECT_NOTE, (note_id,)).fetchone()
        if row is None:
            return None
        return self._to_note(row, self._tags_for([note_id]).get(note_id, []))

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return one page of notes ordered by id and the total number of matching notes."""
        if limit < 1 or offset < 0:
            raise ValueError(f"need limit >= 1 and offset >= 0, got limit={limit}, offset={offset}")
        rows = self._conn.execute(SELECT_PAGE, (tag, tag, limit, offset)).fetchall()
        total = self._conn.execute(COUNT_PAGE, (tag, tag)).fetchone()[0]
        tags = self._tags_for([row["id"] for row in rows])
        return [self._to_note(row, tags.get(row["id"], [])) for row in rows], total

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Merge the sent fields into the stored note and write it back in one transaction."""
        fields = changes.model_dump(exclude_unset=True)
        now = _to_text(self._clock())
        with transaction(self._conn):
            current = self._conn.execute(SELECT_NOTE, (note_id,)).fetchone()
            if current is None:
                return None
            # A fixed column list: unchanged columns are written back with their current values.
            self._conn.execute(
                "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                (fields.get("title", current["title"]), fields.get("body", current["body"]), now, note_id),
            )
            if "tags" in fields:
                self._set_tags(note_id, fields["tags"])
        return self._require(note_id)

    def delete(self, note_id: int) -> bool:
        """Delete the note; ``ON DELETE CASCADE`` removes its ``note_tags`` rows."""
        cursor = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cursor.rowcount == 1

    def _set_tags(self, note_id: int, tags: Sequence[str]) -> None:
        """Replace the tags of ``note_id``. Runs inside the caller's transaction."""
        self._conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        self._conn.executemany(
            "INSERT INTO tags (name) VALUES (?) ON CONFLICT (name) DO NOTHING", [(tag,) for tag in tags]
        )
        self._conn.executemany(
            "INSERT INTO note_tags (note_id, tag_id, position) SELECT ?, id, ? FROM tags WHERE name = ?",
            [(note_id, position, tag) for position, tag in enumerate(tags)],
        )

    def _tags_for(self, note_ids: Sequence[int]) -> dict[int, list[str]]:
        """Fetch the tags of many notes with one query: ``{note_id: [tag, ...]}`` in stored order."""
        if not note_ids:
            return {}
        tags: dict[int, list[str]] = {}
        for note_id, name in self._conn.execute(SELECT_TAGS, (json.dumps(list(note_ids)),)):
            tags.setdefault(note_id, []).append(name)
        return tags

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
# Milestone 5: the HTTP API
# ---------------------------------------------------------------------------


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request, always closed afterwards (even when the handler raises)."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


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
        conn = connect(path)
        try:
            apply_migrations(conn, clock=clock)
        finally:
            conn.close()
        yield

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
    return create_app(Path(os.environ.get("NOTES_DB_PATH", "notes.db")))
