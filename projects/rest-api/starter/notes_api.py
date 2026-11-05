"""Notes & Bookmarks REST API: resource design, validation, status codes, pagination and OpenAPI docs.

Your job is to fill in everything marked ``TODO``, milestone by milestone. Functions that are not
written yet raise ``NotImplementedError``. Run the tests for one milestone with
``python -m pytest -k Milestone1`` (then 2, 3, 4, 5).

The API stores data in memory behind a small repository interface (``NoteRepository`` /
``BookmarkRepository``), so the HTTP layer never knows *where* data lives.

Run it locally and open http://127.0.0.1:8000/docs::

    python -m uvicorn --factory notes_api:create_app --app-dir starter --reload
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
    joined by single hyphens (``TAG_PATTERN``). Raises ``ValueError`` for an invalid tag or more than
    ``MAX_TAGS`` distinct tags (duplicates do not count).
    """
    # TODO(milestone 1): loop over the tags, strip + lower each one, check TAG_PATTERN.fullmatch,
    # skip duplicates, then check the count. Raise ValueError with a helpful message.
    raise NotImplementedError("TODO(milestone 1): normalise_tags")


class NoteCreate(BaseModel):
    """Request body for ``POST /notes``. Unknown fields (such as ``id``) are rejected."""

    # TODO(milestone 1): model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # TODO(milestone 1): title: 1..MAX_TITLE_LENGTH characters; body: default "", at most
    #   MAX_BODY_LENGTH characters. Use Field(min_length=..., max_length=...).
    # TODO(milestone 1): a @field_validator("tags") classmethod that returns normalise_tags(tags).
    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """Request body for ``PATCH /notes/{id}``: only the fields that are sent are changed.

    Sending ``null`` is rejected (leave a field out to keep its value), and at least one field
    must be present, so an empty body is a client error rather than a silent no-op.
    """

    # TODO(milestone 1): the same config and length limits as NoteCreate (the fields stay optional).
    # TODO(milestone 1): normalise tags when they are not None.
    # TODO(milestone 1): a @model_validator(mode="after") that uses self.model_fields_set to reject
    #   an empty update and fields that were sent as null. Return self.
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None


class Note(BaseModel):
    """A stored note, as returned by the API. It should be impossible to change after creation."""

    # TODO(milestone 1): make it immutable: model_config = ConfigDict(frozen=True), and store tags
    #   as tuple[str, ...] (a frozen model can still hold a list that someone appends to).
    id: int
    title: str
    body: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class BookmarkCreate(BaseModel):
    """Request body for ``POST /bookmarks``. Only ``http`` and ``https`` URLs are accepted."""

    # TODO(milestone 1): same config as NoteCreate; url should be an HttpUrl (it normalises the
    #   host to lower case and rejects ftp:, javascript: ...); title 1..MAX_TITLE_LENGTH; normalise tags.
    url: str
    title: str
    tags: list[str] = Field(default_factory=list)


class Bookmark(BaseModel):
    """A stored bookmark. ``url`` is the normalised URL string (lower-case host, trailing slash)."""

    # TODO(milestone 1): immutable, like Note.
    id: int
    url: str
    title: str
    tags: list[str]
    created_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """One page of a collection. ``next_offset`` is ``None`` on the last page. (Provided.)"""

    items: list[T]
    total: int = Field(description="Number of matching items across all pages")
    limit: int
    offset: int
    next_offset: int | None = Field(description="Pass as ?offset= to get the next page; null when done")


class ErrorResponse(BaseModel):
    """The body of every 404 and 409 response. (Provided.)"""

    detail: str = Field(examples=["note 42 not found"])


# ---------------------------------------------------------------------------
# Milestone 2: the repository interface and an in-memory implementation
# ---------------------------------------------------------------------------


@runtime_checkable
class NoteRepository(Protocol):
    """Where notes live. The routes depend on this interface, never on a concrete class. (Provided.)"""

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
        self._lock = threading.Lock()  # FastAPI runs sync endpoints in a thread pool

    def add(self, data: NoteCreate) -> Note:
        """Store a new note. Ids start at 1 and are never reused, even after a delete."""
        # TODO(milestone 2): under self._lock, build a Note with self._next_id and
        #   created_at == updated_at == self._clock(); store it; increment the id; return it.
        raise NotImplementedError("TODO(milestone 2): InMemoryNoteRepository.add")

    def get(self, note_id: int) -> Note | None:
        """Return the note with this id, or ``None``."""
        raise NotImplementedError("TODO(milestone 2): InMemoryNoteRepository.get")

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Note], int]:
        """Return one page of notes in id order and the number of notes that match ``tag``."""
        # TODO(milestone 2): filter by tag (if given), then slice [offset : offset + limit].
        raise NotImplementedError("TODO(milestone 2): InMemoryNoteRepository.page")

    def update(self, note_id: int, changes: NoteUpdate) -> Note | None:
        """Merge the sent fields into the stored note and bump ``updated_at``."""
        # TODO(milestone 2): merge current.model_dump() with changes.model_dump(exclude_unset=True),
        #   set updated_at from the clock, and build a new Note with Note.model_validate(...).
        raise NotImplementedError("TODO(milestone 2): InMemoryNoteRepository.update")

    def delete(self, note_id: int) -> bool:
        """Remove the note; ``True`` if something was deleted."""
        raise NotImplementedError("TODO(milestone 2): InMemoryNoteRepository.delete")


class DuplicateBookmarkError(Exception):
    """Raised when a bookmark with the same normalised URL already exists. (Provided.)"""

    def __init__(self, url: str, existing_id: int) -> None:
        super().__init__(f"a bookmark for {url} already exists (id {existing_id})")
        self.url = url
        self.existing_id = existing_id


@runtime_checkable
class BookmarkRepository(Protocol):
    """Where bookmarks live. (Provided.)"""

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
        # TODO(milestone 5): url = str(data.url); raise DuplicateBookmarkError(url, existing.id) if
        #   any stored bookmark has the same url; otherwise store and return a new Bookmark.
        raise NotImplementedError("TODO(milestone 5): InMemoryBookmarkRepository.add")

    def get(self, bookmark_id: int) -> Bookmark | None:
        """Return the bookmark with this id, or ``None``."""
        raise NotImplementedError("TODO(milestone 5): InMemoryBookmarkRepository.get")

    def page(self, *, offset: int, limit: int, tag: str | None = None) -> tuple[list[Bookmark], int]:
        """Return one page of bookmarks in id order and the match count."""
        raise NotImplementedError("TODO(milestone 5): InMemoryBookmarkRepository.page")

    def delete(self, bookmark_id: int) -> bool:
        """Remove the bookmark; ``True`` if something was deleted."""
        raise NotImplementedError("TODO(milestone 5): InMemoryBookmarkRepository.delete")


# ---------------------------------------------------------------------------
# Dependencies (provided): routes ask for a repository; the app decides which one
# ---------------------------------------------------------------------------


def get_note_repository(request: Request) -> NoteRepository:
    """Return the note repository stored on this app by ``create_app``."""
    return request.app.state.notes


def get_bookmark_repository(request: Request) -> BookmarkRepository:
    """Return the bookmark repository stored on this app by ``create_app``."""
    return request.app.state.bookmarks


NoteRepo = Annotated[NoteRepository, Depends(get_note_repository)]
BookmarkRepo = Annotated[BookmarkRepository, Depends(get_bookmark_repository)]
# TODO(milestone 3): ids are positive: add ge=1 to both Path(...) declarations.
NoteId = Annotated[int, Path(description="The note's id")]
BookmarkId = Annotated[int, Path(description="The bookmark's id")]
# TODO(milestone 4): limit must be 1..MAX_PAGE_SIZE and offset >= 0 (Query(ge=..., le=...)).
Limit = Annotated[int, Query(description="Page size (1-100)")]
Offset = Annotated[int, Query(description="Number of items to skip")]
TagFilter = Annotated[str | None, Query(max_length=50, description="Only items with this tag")]


def not_found(kind: str, item_id: int) -> HTTPException:
    """A 404 with the standard ``{"detail": "<kind> <id> not found"}`` body. (Provided.)"""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} {item_id} not found")


def clean_tag(tag: str | None) -> str | None:
    """Normalise a ``?tag=`` filter the same way stored tags are normalised. (Provided.)"""
    return tag.strip().lower() if tag is not None else None


# ---------------------------------------------------------------------------
# Milestones 3 and 4: note endpoints, status codes and pagination
# ---------------------------------------------------------------------------


def next_offset(total: int, limit: int, offset: int) -> int | None:
    """The offset of the next page, or ``None`` if this page reaches the end."""
    raise NotImplementedError("TODO(milestone 4): next_offset")


NOTE_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "There is no note with this id"}
}


def build_notes_router() -> APIRouter:
    """The ``/notes`` resource: create, list, read, partially update and delete."""
    router = APIRouter(prefix="/notes", tags=["notes"])

    # TODO(milestone 3): status_code=status.HTTP_201_CREATED and summary="Create a note" in the decorator.
    @router.post("")
    def create_note(data: NoteCreate, request: Request, response: Response, repo: NoteRepo) -> Note:
        # TODO(milestone 3): note = repo.add(data); set the Location header with
        #   str(request.url_for("get_note", note_id=note.id)); return the note.
        raise NotImplementedError("TODO(milestone 3): create_note")

    # TODO(milestone 5): add a summary to every route decorator.
    @router.get("")
    def list_notes(
        repo: NoteRepo, limit: Limit = DEFAULT_PAGE_SIZE, offset: Offset = 0, tag: TagFilter = None
    ) -> Page[Note]:
        # TODO(milestone 4): items, total = repo.page(...) with clean_tag(tag); return a Page[Note]
        #   that includes next_offset(total, limit, offset).
        raise NotImplementedError("TODO(milestone 4): list_notes")

    # TODO(milestone 5): document the 404 with responses=NOTE_NOT_FOUND (also on PATCH and DELETE).
    @router.get("/{note_id}")
    def get_note(note_id: NoteId, repo: NoteRepo) -> Note:
        # TODO(milestone 3): return the note or raise not_found("note", note_id).
        raise NotImplementedError("TODO(milestone 3): get_note")

    @router.patch("/{note_id}")
    def update_note(note_id: NoteId, changes: NoteUpdate, repo: NoteRepo) -> Note:
        # TODO(milestone 3): repo.update(...) or 404.
        raise NotImplementedError("TODO(milestone 3): update_note")

    # TODO(milestone 3): status_code=status.HTTP_204_NO_CONTENT and response_class=Response.
    @router.delete("/{note_id}")
    def delete_note(note_id: NoteId, repo: NoteRepo) -> Response:
        # TODO(milestone 3): 404 if repo.delete(...) is False, else Response(status_code=204).
        raise NotImplementedError("TODO(milestone 3): delete_note")

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
    # TODO(milestone 5): add four routes, following the notes router:
    #   POST ""               create_bookmark  -> 201 + Location; DuplicateBookmarkError -> 409
    #   GET  ""               list_bookmarks   -> Page[Bookmark] (limit, offset, tag)
    #   GET  "/{bookmark_id}" get_bookmark     -> 200 or 404 "bookmark <id> not found"
    #   DELETE "/{bookmark_id}" delete_bookmark -> 204 or 404
    #   Document errors with responses=BOOKMARK_CONFLICT / BOOKMARK_NOT_FOUND and give each a summary.
    return router


def operation_id(route: APIRoute) -> str:
    """Use the route function's name (``create_note``) as its OpenAPI operationId."""
    raise NotImplementedError("TODO(milestone 5): operation_id")


def create_app(
    notes: NoteRepository | None = None,
    bookmarks: BookmarkRepository | None = None,
    clock: Clock = utc_now,
) -> FastAPI:
    """Build the API. Pass repositories to share or pre-fill data; by default each app gets its own."""
    # TODO(milestone 5): add description=..., openapi_tags=[{"name": "notes", "description": ...},
    #   {"name": "bookmarks", "description": ...}] and generate_unique_id_function=operation_id.
    app = FastAPI(title="Notes & Bookmarks API", version=API_VERSION)
    app.state.notes = notes if notes is not None else InMemoryNoteRepository(clock)
    app.state.bookmarks = bookmarks if bookmarks is not None else InMemoryBookmarkRepository(clock)
    app.include_router(build_notes_router())
    app.include_router(build_bookmarks_router())
    return app
