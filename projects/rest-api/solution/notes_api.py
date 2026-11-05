"""Notes & Bookmarks REST API: resource design, validation, status codes, pagination and OpenAPI docs.

The API stores data in memory behind a small repository interface (``NoteRepository`` /
``BookmarkRepository``), so the HTTP layer never knows *where* data lives. The
``crud-database-app`` project swaps the in-memory repository for SQLite without touching the routes.

Run it locally and open http://127.0.0.1:8000/docs::

    python -m uvicorn --factory notes_api:create_app --app-dir solution --reload
"""

import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Generic, Protocol, Self, TypeVar, runtime_checkable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

API_VERSION = "1.0.0"
MAX_TAGS = 10
MAX_TITLE_LENGTH = 200
MAX_BODY_LENGTH = 10_000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

Clock = Callable[[], datetime]
"""Returns the current time as an aware UTC datetime. Injected so tests can control time."""


def utc_now() -> datetime:
    """The default clock: the current time in UTC."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Milestone 1: models and validation
# ---------------------------------------------------------------------------


def normalise_tags(tags: list[str]) -> list[str]:
    """Return ``tags`` stripped, lower-cased and de-duplicated (first occurrence wins).

    Each tag must look like ``python`` or ``web-dev``: lowercase letters and digits, optionally
    joined by single hyphens. Raises ``ValueError`` for an invalid tag or more than ``MAX_TAGS``
    distinct tags.
    """
    result: list[str] = []
    for raw in tags:
        tag = raw.strip().lower()
        if not TAG_PATTERN.fullmatch(tag):
            raise ValueError(f"invalid tag {raw!r}: use lowercase letters, digits and single hyphens")
        if tag not in result:
            result.append(tag)
    if len(result) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} distinct tags are allowed, got {len(result)}")
    return result


class NoteCreate(BaseModel):
    """Request body for ``POST /notes``. Unknown fields (such as ``id``) are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH, examples=["Read the FastAPI tutorial"])
    body: str = Field(default="", max_length=MAX_BODY_LENGTH, examples=["Start with path parameters."])
    tags: list[str] = Field(default_factory=list, examples=[["python", "web-dev"]])

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str]) -> list[str]:
        return normalise_tags(tags)


class NoteUpdate(BaseModel):
    """Request body for ``PATCH /notes/{id}``: only the fields that are sent are changed.

    Sending ``null`` is rejected (leave a field out to keep its value), and at least one field
    must be present, so an empty body is a client error rather than a silent no-op.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    body: str | None = Field(default=None, max_length=MAX_BODY_LENGTH)
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else normalise_tags(tags)

    @model_validator(mode="after")
    def _check_sent_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one of: title, body, tags")
        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null; leave a field out to keep its value")
        return self


class Note(BaseModel):
    """A stored note, as returned by the API. Frozen (and ``tags`` is a tuple) so it cannot change."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    body: str
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class BookmarkCreate(BaseModel):
    """Request body for ``POST /bookmarks``. ``HttpUrl`` accepts only ``http`` and ``https`` URLs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: HttpUrl = Field(examples=["https://fastapi.tiangolo.com/tutorial/"])
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH, examples=["FastAPI tutorial"])
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _normalise_tags(cls, tags: list[str]) -> list[str]:
        return normalise_tags(tags)


class Bookmark(BaseModel):
    """A stored bookmark. ``url`` is the normalised URL string (lower-case host, trailing slash)."""

    model_config = ConfigDict(frozen=True)

    id: int
    url: str
    title: str
    tags: tuple[str, ...]
    created_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a collection. ``next_offset`` is ``None`` on the last page."""

    items: list[T]
    total: int = Field(description="Number of matching items across all pages")
    limit: int
    offset: int
    next_offset: int | None = Field(description="Pass as ?offset= to get the next page; null when done")


class ErrorResponse(BaseModel):
    """The body of every 404 and 409 response."""

    detail: str = Field(examples=["note 42 not found"])


# ---------------------------------------------------------------------------
# Milestone 2: the repository interface and an in-memory implementation
# ---------------------------------------------------------------------------


@runtime_checkable
class NoteRepository(Protocol):
    """Where notes live. The routes depend on this interface, never on a concrete class."""

    def add(self, data: NoteCreate) -> Note:
        """Store a new note and return it with its id and timestamps."""
        ...

    def get(self, note_id: int) -> Note | None:
        """Return the note, or ``None`` if there is no note with this id."""
        ...

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return ``(items, total)``: up to ``limit`` notes in id order and the number that match."""
        ...

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Apply the fields that were sent; return the new note or ``None`` if it does not exist."""
        ...

    def delete(self, note_id: int) -> bool:
        """Delete the note; return ``False`` if it did not exist."""
        ...


class InMemoryNoteRepository:
    """A thread-safe, in-memory ``NoteRepository``. Create one per app (or per test)."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._notes: dict[int, Note] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def add(self, data: NoteCreate) -> Note:
        """Store a new note. Ids start at 1 and are never reused, even after a delete."""
        with self._lock:
            now = self._clock()
            note = Note(
                id=self._next_id,
                title=data.title,
                body=data.body,
                tags=tuple(data.tags),
                created_at=now,
                updated_at=now,
            )
            self._notes[note.id] = note
            self._next_id += 1
            return note

    def get(self, note_id: int) -> Note | None:
        """Return the note with this id, or ``None``."""
        with self._lock:
            return self._notes.get(note_id)

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return one page of notes in id order (dicts keep insertion order) and the match count."""
        with self._lock:
            matching = [note for note in self._notes.values() if tag is None or tag in note.tags]
        return matching[offset : offset + limit], len(matching)

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Merge the sent fields into the stored note and bump ``updated_at``."""
        with self._lock:
            current = self._notes.get(note_id)
            if current is None:
                return None
            merged = {**current.model_dump(), **changes.model_dump(exclude_unset=True)}
            merged["updated_at"] = self._clock()
            updated = Note.model_validate(merged)
            self._notes[note_id] = updated
            return updated

    def delete(self, note_id: int) -> bool:
        """Remove the note; ``True`` if something was deleted."""
        with self._lock:
            return self._notes.pop(note_id, None) is not None


class DuplicateBookmarkError(Exception):
    """Raised when a bookmark with the same normalised URL already exists."""

    def __init__(self, url: str, existing_id: int) -> None:
        super().__init__(f"a bookmark for {url} already exists (id {existing_id})")
        self.url = url
        self.existing_id = existing_id


@runtime_checkable
class BookmarkRepository(Protocol):
    """Where bookmarks live."""

    def add(self, data: BookmarkCreate) -> Bookmark:
        """Store a bookmark; raise ``DuplicateBookmarkError`` if the URL is already saved."""
        ...

    def get(self, bookmark_id: int) -> Bookmark | None:
        """Return the bookmark, or ``None``."""
        ...

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Bookmark], int]:
        """Return ``(items, total)`` in id order."""
        ...

    def delete(self, bookmark_id: int) -> bool:
        """Delete the bookmark; return ``False`` if it did not exist."""
        ...


class InMemoryBookmarkRepository:
    """A thread-safe, in-memory ``BookmarkRepository`` with one bookmark per normalised URL."""

    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._bookmarks: dict[int, Bookmark] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def add(self, data: BookmarkCreate) -> Bookmark:
        """Store a bookmark, refusing a URL that is already saved."""
        url = str(data.url)
        with self._lock:
            for existing in self._bookmarks.values():
                if existing.url == url:
                    raise DuplicateBookmarkError(url, existing.id)
            bookmark = Bookmark(
                id=self._next_id, url=url, title=data.title, tags=tuple(data.tags), created_at=self._clock()
            )
            self._bookmarks[bookmark.id] = bookmark
            self._next_id += 1
            return bookmark

    def get(self, bookmark_id: int) -> Bookmark | None:
        """Return the bookmark with this id, or ``None``."""
        with self._lock:
            return self._bookmarks.get(bookmark_id)

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Bookmark], int]:
        """Return one page of bookmarks in id order and the match count."""
        with self._lock:
            matching = [b for b in self._bookmarks.values() if tag is None or tag in b.tags]
        return matching[offset : offset + limit], len(matching)

    def delete(self, bookmark_id: int) -> bool:
        """Remove the bookmark; ``True`` if something was deleted."""
        with self._lock:
            return self._bookmarks.pop(bookmark_id, None) is not None


# ---------------------------------------------------------------------------
# Dependencies: routes ask for a repository; the app decides which one
# ---------------------------------------------------------------------------


def get_note_repository(request: Request) -> NoteRepository:
    """Return the note repository stored on this app by ``create_app``."""
    return request.app.state.notes


def get_bookmark_repository(request: Request) -> BookmarkRepository:
    """Return the bookmark repository stored on this app by ``create_app``."""
    return request.app.state.bookmarks


NoteRepo = Annotated[NoteRepository, Depends(get_note_repository)]
BookmarkRepo = Annotated[BookmarkRepository, Depends(get_bookmark_repository)]
NoteId = Annotated[int, Path(ge=1, description="The note's id")]
BookmarkId = Annotated[int, Path(ge=1, description="The bookmark's id")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Page size (1-100)")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip")]
TagFilter = Annotated[str | None, Query(max_length=50, description="Only items with this tag")]


def not_found(kind: str, item_id: int) -> HTTPException:
    """A 404 with the standard ``{"detail": "<kind> <id> not found"}`` body."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} {item_id} not found")


def clean_tag(tag: str | None) -> str | None:
    """Normalise a ``?tag=`` filter the same way stored tags are normalised."""
    return tag.strip().lower() if tag is not None else None


# ---------------------------------------------------------------------------
# Milestones 3 and 4: note endpoints, status codes and pagination
# ---------------------------------------------------------------------------


def next_offset(total: int, limit: int, offset: int) -> int | None:
    """The offset of the next page, or ``None`` if this page reaches the end."""
    following = offset + limit
    return following if following < total else None


NOTE_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "There is no note with this id"}
}


def build_notes_router() -> APIRouter:
    """The ``/notes`` resource: create, list, read, partially update and delete."""
    router = APIRouter(prefix="/notes", tags=["notes"])

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        summary="Create a note",
        response_description="The created note; its URL is in the Location header",
    )
    def create_note(data: NoteCreate, request: Request, response: Response, repo: NoteRepo) -> Note:
        note = repo.add(data)
        response.headers["Location"] = str(request.url_for("get_note", note_id=note.id))
        return note

    @router.get("", summary="List notes, newest id last, one page at a time")
    def list_notes(
        repo: NoteRepo, limit: Limit = DEFAULT_PAGE_SIZE, offset: Offset = 0, tag: TagFilter = None
    ) -> Page[Note]:
        items, total = repo.page(offset=offset, limit=limit, tag=clean_tag(tag))
        return Page[Note](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            next_offset=next_offset(total, limit, offset),
        )

    @router.get("/{note_id}", summary="Get one note", responses=NOTE_NOT_FOUND)
    def get_note(note_id: NoteId, repo: NoteRepo) -> Note:
        note = repo.get(note_id)
        if note is None:
            raise not_found("note", note_id)
        return note

    @router.patch("/{note_id}", summary="Change some fields of a note", responses=NOTE_NOT_FOUND)
    def update_note(note_id: NoteId, changes: NoteUpdate, repo: NoteRepo) -> Note:
        note = repo.update(note_id, changes)
        if note is None:
            raise not_found("note", note_id)
        return note

    @router.delete(
        "/{note_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a note",
        responses=NOTE_NOT_FOUND,
        response_class=Response,
    )
    def delete_note(note_id: NoteId, repo: NoteRepo) -> Response:
        if not repo.delete(note_id):
            raise not_found("note", note_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


# ---------------------------------------------------------------------------
# Milestone 5: a second resource, and OpenAPI documentation
# ---------------------------------------------------------------------------

BOOKMARK_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "There is no bookmark with this id"}
}
BOOKMARK_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "This URL is already bookmarked"}
}


def build_bookmarks_router() -> APIRouter:
    """The ``/bookmarks`` resource: create (unique URL), list, read and delete."""
    router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        summary="Bookmark a URL",
        responses=BOOKMARK_CONFLICT,
        response_description="The created bookmark; its URL is in the Location header",
    )
    def create_bookmark(
        data: BookmarkCreate, request: Request, response: Response, repo: BookmarkRepo
    ) -> Bookmark:
        try:
            bookmark = repo.add(data)
        except DuplicateBookmarkError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        response.headers["Location"] = str(request.url_for("get_bookmark", bookmark_id=bookmark.id))
        return bookmark

    @router.get("", summary="List bookmarks, one page at a time")
    def list_bookmarks(
        repo: BookmarkRepo, limit: Limit = DEFAULT_PAGE_SIZE, offset: Offset = 0, tag: TagFilter = None
    ) -> Page[Bookmark]:
        items, total = repo.page(offset=offset, limit=limit, tag=clean_tag(tag))
        return Page[Bookmark](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            next_offset=next_offset(total, limit, offset),
        )

    @router.get("/{bookmark_id}", summary="Get one bookmark", responses=BOOKMARK_NOT_FOUND)
    def get_bookmark(bookmark_id: BookmarkId, repo: BookmarkRepo) -> Bookmark:
        bookmark = repo.get(bookmark_id)
        if bookmark is None:
            raise not_found("bookmark", bookmark_id)
        return bookmark

    @router.delete(
        "/{bookmark_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a bookmark",
        responses=BOOKMARK_NOT_FOUND,
        response_class=Response,
    )
    def delete_bookmark(bookmark_id: BookmarkId, repo: BookmarkRepo) -> Response:
        if not repo.delete(bookmark_id):
            raise not_found("bookmark", bookmark_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


API_DESCRIPTION = """
Save short **notes** and **bookmarks**, tag them, and page through them.

* Collections are paginated with `limit` (1-100, default 20) and `offset`; follow `next_offset`.
* Errors use the status code that says what went wrong: 404 (no such item), 409 (duplicate),
  422 (the request body or parameters are invalid; `detail[].loc` points at the field).
"""

OPENAPI_TAGS = [
    {"name": "notes", "description": "Short text notes with tags. Supports partial updates (PATCH)."},
    {"name": "bookmarks", "description": "Saved links. Each URL can be bookmarked once."},
]


def operation_id(route: APIRoute) -> str:
    """Use the route function's name (``create_note``) as its OpenAPI operationId."""
    return route.name


def create_app(
    notes: NoteRepository | None = None,
    bookmarks: BookmarkRepository | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    """Build the API. Pass repositories to share or pre-fill data; by default each app gets its own."""
    app = FastAPI(
        title="Notes & Bookmarks API",
        version=API_VERSION,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        generate_unique_id_function=operation_id,
    )
    app.state.notes = notes if notes is not None else InMemoryNoteRepository(clock)
    app.state.bookmarks = bookmarks if bookmarks is not None else InMemoryBookmarkRepository(clock)
    app.include_router(build_notes_router())
    app.include_router(build_bookmarks_router())
    return app
