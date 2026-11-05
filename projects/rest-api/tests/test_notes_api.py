"""Behaviour tests for the Notes & Bookmarks API, grouped by milestone.

Run one milestone with:  python -m pytest -k Milestone1
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import notes_api as api
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

START = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class FakeClock:
    """A controllable clock: tests move time forward instead of sleeping."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def notes(clock: FakeClock) -> api.InMemoryNoteRepository:
    return api.InMemoryNoteRepository(clock)


@pytest.fixture
def client(clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(api.create_app(clock=clock)) as test_client:
        yield test_client


def create_note(client: TestClient, title: str = "Groceries", **fields: object) -> dict:
    """POST a note and return its JSON, failing the test with a clear message if it was not created."""
    response = client.post("/notes", json={"title": title, **fields})
    assert response.status_code == 201, (
        f"POST /notes should return 201, got {response.status_code}: {response.text}"
    )
    return response.json()


def ids(page: dict) -> list[int]:
    return [item["id"] for item in page["items"]]


def error_locations(response) -> list[list]:
    """The ``loc`` of every validation error in a 422 response."""
    return [error["loc"] for error in response.json()["detail"]]


# ---------------------------------------------------------------------------
# Milestone 1: models and validation
# ---------------------------------------------------------------------------


class TestMilestone1Models:
    def test_normalise_tags_strips_lowercases_and_deduplicates(self) -> None:
        result = api.normalise_tags([" Python", "python", "FastAPI ", "web-dev"])
        assert result == ["python", "fastapi", "web-dev"], (
            f"tags should be stripped, lower-cased and de-duplicated in first-seen order, got {result!r}"
        )

    @pytest.mark.parametrize(
        "bad", ["has space", "under_score", "-leading", "trailing-", "double--dash", "", "é"]
    )
    def test_normalise_tags_rejects_invalid_tags(self, bad: str) -> None:
        with pytest.raises(ValueError, match="tag"):
            api.normalise_tags([bad])

    def test_normalise_tags_allows_ten_distinct_tags_but_not_eleven(self) -> None:
        ten = [f"tag{i}" for i in range(10)]
        assert api.normalise_tags(ten + ["TAG0", "tag1"]) == ten, (
            "duplicates must not count towards the limit"
        )
        with pytest.raises(ValueError, match="10"):
            api.normalise_tags([*ten, "tag10"])

    def test_note_create_strips_title_and_applies_defaults(self) -> None:
        note = api.NoteCreate(title="  Groceries  ")
        assert note.title == "Groceries", "use str_strip_whitespace so titles are stripped"
        assert note.body == "", "body should default to an empty string"
        assert note.tags == [], "tags should default to an empty list"

    @pytest.mark.parametrize("title", ["", "   ", "x" * 201])
    def test_note_create_rejects_empty_or_long_titles(self, title: str) -> None:
        with pytest.raises(ValidationError) as excinfo:
            api.NoteCreate(title=title)
        assert excinfo.value.errors()[0]["loc"] == ("title",)

    def test_note_create_limits(self) -> None:
        assert api.NoteCreate(title="x" * 200).title == "x" * 200, (
            "200 characters is the maximum, not too long"
        )
        with pytest.raises(ValidationError):
            api.NoteCreate(title="ok", body="b" * 10_001)

    def test_note_create_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            api.NoteCreate.model_validate({"title": "Hi", "id": 99})
        assert excinfo.value.errors()[0]["type"] == "extra_forbidden", (
            "clients must not choose their own id: set extra='forbid' on NoteCreate"
        )

    def test_note_create_normalises_and_validates_tags(self) -> None:
        assert api.NoteCreate(title="t", tags=["API", "api", "Web-Dev"]).tags == ["api", "web-dev"]
        with pytest.raises(ValidationError) as excinfo:
            api.NoteCreate(title="t", tags=["not ok"])
        assert excinfo.value.errors()[0]["loc"] == ("tags",), "tag errors should point at the tags field"

    def test_note_update_remembers_which_fields_were_sent(self) -> None:
        update = api.NoteUpdate(body="new body")
        assert update.model_dump(exclude_unset=True) == {"body": "new body"}, (
            "a PATCH must only contain the fields the client sent"
        )

    @pytest.mark.parametrize("payload", [{}, {"title": None}, {"tags": None}, {"colour": "red"}])
    def test_note_update_rejects_empty_null_and_unknown(self, payload: dict) -> None:
        with pytest.raises(ValidationError):
            api.NoteUpdate.model_validate(payload)

    @pytest.mark.parametrize(
        "url", ["ftp://example.com/file", "javascript:alert(1)", "not a url", "example.com"]
    )
    def test_bookmark_create_accepts_only_http_urls(self, url: str) -> None:
        with pytest.raises(ValidationError):
            api.BookmarkCreate(url=url, title="Link")

    def test_bookmark_create_normalises_url(self) -> None:
        bookmark = api.BookmarkCreate(url="https://Example.com", title="Example")
        assert str(bookmark.url) == "https://example.com/"

    def test_note_is_immutable(self) -> None:
        note = api.Note(id=1, title="t", body="", tags=["a"], created_at=START, updated_at=START)
        assert note.tags == ("a",), "store tags as a tuple so nobody can append to a stored note"
        with pytest.raises(ValidationError):
            note.title = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Milestone 2: repository interface and in-memory implementation
# ---------------------------------------------------------------------------


class TestMilestone2Repository:
    def test_in_memory_repositories_implement_the_interfaces(self, clock: FakeClock) -> None:
        assert isinstance(api.InMemoryNoteRepository(clock), api.NoteRepository)
        assert isinstance(api.InMemoryBookmarkRepository(clock), api.BookmarkRepository)

    def test_add_assigns_sequential_ids_and_clock_timestamps(self, notes, clock: FakeClock) -> None:
        first = notes.add(api.NoteCreate(title="First", tags=["a"]))
        clock.advance(5)
        second = notes.add(api.NoteCreate(title="Second"))
        assert (first.id, second.id) == (1, 2), "ids should start at 1 and go up by one"
        assert first.created_at == first.updated_at == START, "timestamps must come from the injected clock"
        assert second.created_at == START + timedelta(seconds=5)
        assert first.tags == ("a",)

    def test_get_returns_the_note_or_none(self, notes) -> None:
        added = notes.add(api.NoteCreate(title="Keep me"))
        assert notes.get(added.id) == added
        assert notes.get(999) is None, "a missing id should return None, not raise"

    def test_update_changes_only_sent_fields_and_bumps_updated_at(self, notes, clock: FakeClock) -> None:
        note = notes.add(api.NoteCreate(title="Draft", body="original", tags=["x"]))
        clock.advance(60)
        updated = notes.update(note.id, api.NoteUpdate(title="Final"))
        assert updated is not None
        assert (updated.title, updated.body, updated.tags) == ("Final", "original", ("x",))
        assert updated.created_at == START, "created_at must never change"
        assert updated.updated_at == START + timedelta(seconds=60), "updated_at should come from the clock"
        assert notes.get(note.id) == updated, "the update must be stored, not just returned"

    def test_update_can_replace_tags(self, notes) -> None:
        note = notes.add(api.NoteCreate(title="t", tags=["old"]))
        updated = notes.update(note.id, api.NoteUpdate(tags=["new", "NEW", "other"]))
        assert updated is not None and updated.tags == ("new", "other")

    def test_update_missing_returns_none(self, notes) -> None:
        assert notes.update(42, api.NoteUpdate(title="x")) is None

    def test_delete_reports_whether_something_was_deleted(self, notes) -> None:
        note = notes.add(api.NoteCreate(title="Bye"))
        assert notes.delete(note.id) is True
        assert notes.get(note.id) is None
        assert notes.delete(note.id) is False, "deleting twice should return False the second time"

    def test_ids_are_never_reused(self, notes) -> None:
        notes.add(api.NoteCreate(title="one"))
        two = notes.add(api.NoteCreate(title="two"))
        notes.delete(two.id)
        three = notes.add(api.NoteCreate(title="three"))
        assert three.id == 3, f"an id that was deleted must not be handed out again, got {three.id}"

    def test_page_returns_items_in_id_order_with_total(self, notes) -> None:
        for i in range(5):
            notes.add(api.NoteCreate(title=f"n{i}", tags=["even" if i % 2 == 0 else "odd"]))
        items, total = notes.page(offset=1, limit=2)
        assert [n.id for n in items] == [2, 3] and total == 5
        even, even_total = notes.page(offset=0, limit=10, tag="even")
        assert [n.id for n in even] == [1, 3, 5] and even_total == 3

    def test_returned_notes_cannot_change_the_store(self, notes) -> None:
        note = notes.add(api.NoteCreate(title="Safe", tags=["a"]))
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            note.tags.append("b")  # type: ignore[attr-defined]
        assert notes.get(note.id).tags == ("a",)


# ---------------------------------------------------------------------------
# Milestone 3: CRUD endpoints and status codes
# ---------------------------------------------------------------------------


class TestMilestone3Endpoints:
    def test_create_returns_201_with_location_and_body(self, client: TestClient) -> None:
        response = client.post("/notes", json={"title": "Groceries", "body": "eggs", "tags": ["Home"]})
        assert response.status_code == 201, (
            f"creating a resource should return 201, got {response.status_code}"
        )
        assert response.headers.get("location", "").endswith("/notes/1"), (
            "set the Location header to the new note's URL (use request.url_for)"
        )
        assert response.json() == {
            "id": 1,
            "title": "Groceries",
            "body": "eggs",
            "tags": ["home"],
            "created_at": "2026-01-15T09:30:00Z",
            "updated_at": "2026-01-15T09:30:00Z",
        }

    def test_get_one_note(self, client: TestClient) -> None:
        created = create_note(client, "Read")
        response = client.get(f"/notes/{created['id']}")
        assert response.status_code == 200
        assert response.json() == created

    def test_missing_note_is_404_with_detail(self, client: TestClient) -> None:
        response = client.get("/notes/999")
        assert response.status_code == 404
        assert response.json() == {"detail": "note 999 not found"}

    @pytest.mark.parametrize("bad_id", ["abc", "0", "-3"])
    def test_invalid_note_id_is_422(self, client: TestClient, bad_id: str) -> None:
        response = client.get(f"/notes/{bad_id}")
        assert response.status_code == 422, "ids are positive integers: use Path(ge=1)"
        assert error_locations(response) == [["path", "note_id"]]

    def test_invalid_body_is_422_pointing_at_the_field(self, client: TestClient) -> None:
        response = client.post("/notes", json={"title": "   "})
        assert response.status_code == 422
        assert error_locations(response) == [["body", "title"]]

    def test_client_cannot_set_the_id(self, client: TestClient) -> None:
        response = client.post("/notes", json={"title": "Sneaky", "id": 1000})
        assert response.status_code == 422
        assert ["body", "id"] in error_locations(response)

    def test_patch_changes_only_sent_fields(self, client: TestClient, clock: FakeClock) -> None:
        created = create_note(client, "Draft", body="keep me", tags=["x"])
        clock.advance(90)
        response = client.patch(f"/notes/{created['id']}", json={"title": "Final"})
        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["body"], body["tags"]) == ("Final", "keep me", ["x"])
        assert body["updated_at"] == "2026-01-15T09:31:30Z"
        assert body["created_at"] == created["created_at"]

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [({"title": "x"}, 404), ({}, 422), ({"title": None}, 422), ({"pinned": True}, 422)],
    )
    def test_patch_errors(self, client: TestClient, payload: dict, expected: int) -> None:
        create_note(client)
        target = "/notes/999" if expected == 404 else "/notes/1"
        response = client.patch(target, json=payload)
        assert response.status_code == expected, f"PATCH {target} {payload} should be {expected}"

    def test_delete_returns_204_then_404(self, client: TestClient) -> None:
        created = create_note(client)
        response = client.delete(f"/notes/{created['id']}")
        assert response.status_code == 204, "a successful DELETE with no body should return 204"
        assert response.content == b"", "a 204 response must not have a body"
        assert client.get(f"/notes/{created['id']}").status_code == 404
        assert client.delete(f"/notes/{created['id']}").status_code == 404

    def test_unsupported_method_is_405(self, client: TestClient) -> None:
        create_note(client)
        assert client.put("/notes/1", json={"title": "x"}).status_code == 405, (
            "this API supports PATCH, not PUT, on a note"
        )

    def test_app_uses_the_injected_repository(self, clock: FakeClock) -> None:
        repo = api.InMemoryNoteRepository(clock)
        repo.add(api.NoteCreate(title="Pre-loaded"))
        with TestClient(api.create_app(notes=repo, clock=clock)) as test_client:
            assert test_client.get("/notes/1").json()["title"] == "Pre-loaded"
            create_note(test_client, "Through the API")
        assert repo.get(2) is not None, "notes created over HTTP must land in the injected repository"

    def test_apps_do_not_share_state(self, clock: FakeClock) -> None:
        with (
            TestClient(api.create_app(clock=clock)) as first,
            TestClient(api.create_app(clock=clock)) as second,
        ):
            create_note(first)
            assert second.get("/notes/1").status_code == 404, "each app needs its own repository (no globals)"


# ---------------------------------------------------------------------------
# Milestone 4: pagination and filtering
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_25(client: TestClient) -> TestClient:
    for i in range(1, 26):
        create_note(client, f"Note {i}", tags=["python"] if i % 5 == 0 else [])
    return client


class TestMilestone4Pagination:
    @pytest.mark.parametrize(
        ("total", "limit", "offset", "expected"),
        [
            (25, 20, 0, 20),
            (25, 20, 20, None),
            (20, 20, 0, None),
            (0, 20, 0, None),
            (25, 10, 10, 20),
            (5, 10, 30, None),
        ],
    )
    def test_next_offset(self, total: int, limit: int, offset: int, expected: int | None) -> None:
        assert api.next_offset(total, limit, offset) == expected

    def test_default_page(self, client_with_25: TestClient) -> None:
        page = client_with_25.get("/notes").json()
        assert ids(page) == list(range(1, 21)), "the default page size is 20, in id order"
        assert (page["total"], page["limit"], page["offset"], page["next_offset"]) == (25, 20, 0, 20)

    def test_last_page_has_no_next_offset(self, client_with_25: TestClient) -> None:
        page = client_with_25.get("/notes", params={"offset": 20}).json()
        assert ids(page) == [21, 22, 23, 24, 25]
        assert page["next_offset"] is None, "next_offset must be null on the last page"

    def test_custom_limit_and_offset(self, client_with_25: TestClient) -> None:
        page = client_with_25.get("/notes", params={"limit": 10, "offset": 10}).json()
        assert ids(page) == list(range(11, 21)) and page["next_offset"] == 20

    @pytest.mark.parametrize(
        ("params", "field"), [({"limit": 0}, "limit"), ({"limit": 101}, "limit"), ({"offset": -1}, "offset")]
    )
    def test_out_of_range_parameters_are_422(self, client: TestClient, params: dict, field: str) -> None:
        response = client.get("/notes", params=params)
        assert response.status_code == 422, f"{params} is out of range and must be rejected"
        assert error_locations(response) == [["query", field]]

    def test_maximum_limit_is_allowed(self, client_with_25: TestClient) -> None:
        response = client_with_25.get("/notes", params={"limit": 100})
        assert response.status_code == 200 and len(response.json()["items"]) == 25

    def test_offset_past_the_end_is_an_empty_page(self, client_with_25: TestClient) -> None:
        page = client_with_25.get("/notes", params={"offset": 500}).json()
        assert page["items"] == [] and page["total"] == 25 and page["next_offset"] is None

    def test_tag_filter_is_case_insensitive_and_counts_matches(self, client_with_25: TestClient) -> None:
        lower = client_with_25.get("/notes", params={"tag": "python"}).json()
        upper = client_with_25.get("/notes", params={"tag": " PYTHON "}).json()
        assert ids(lower) == [5, 10, 15, 20, 25] and lower["total"] == 5
        assert ids(upper) == ids(lower), "normalise ?tag= the same way stored tags are normalised"

    def test_tag_filter_with_pagination(self, client_with_25: TestClient) -> None:
        page = client_with_25.get("/notes", params={"tag": "python", "limit": 2, "offset": 2}).json()
        assert ids(page) == [15, 20] and page["total"] == 5 and page["next_offset"] == 4

    def test_walking_all_pages_returns_every_note_once(self, client_with_25: TestClient) -> None:
        client_with_25.delete("/notes/2")
        seen: list[int] = []
        offset: int | None = 0
        while offset is not None:
            page = client_with_25.get("/notes", params={"limit": 7, "offset": offset}).json()
            seen.extend(ids(page))
            offset = page["next_offset"]
        assert seen == [i for i in range(1, 26) if i != 2], "pages must be in a stable order with no gaps"


# ---------------------------------------------------------------------------
# Milestone 5: bookmarks and OpenAPI documentation
# ---------------------------------------------------------------------------


@pytest.fixture
def openapi(client: TestClient) -> dict:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


class TestMilestone5BookmarksAndDocs:
    def test_create_bookmark_normalises_url(self, client: TestClient) -> None:
        response = client.post(
            "/bookmarks", json={"url": "https://Example.com", "title": "Example", "tags": ["Ref"]}
        )
        assert response.status_code == 201
        assert response.headers.get("location", "").endswith("/bookmarks/1")
        body = response.json()
        assert (body["id"], body["url"], body["tags"]) == (1, "https://example.com/", ["ref"])

    def test_duplicate_url_is_409(self, client: TestClient) -> None:
        client.post("/bookmarks", json={"url": "https://example.com/", "title": "First"})
        response = client.post("/bookmarks", json={"url": "https://EXAMPLE.com", "title": "Again"})
        assert response.status_code == 409, "the same normalised URL must not be saved twice"
        assert "id 1" in response.json()["detail"], "say which bookmark already has this URL"

    def test_repository_raises_duplicate_error(self, clock: FakeClock) -> None:
        repo = api.InMemoryBookmarkRepository(clock)
        repo.add(api.BookmarkCreate(url="https://example.com", title="One"))
        with pytest.raises(api.DuplicateBookmarkError) as excinfo:
            repo.add(api.BookmarkCreate(url="https://example.com/", title="Two"))
        assert excinfo.value.existing_id == 1

    def test_invalid_url_is_422(self, client: TestClient) -> None:
        response = client.post("/bookmarks", json={"url": "javascript:alert(1)", "title": "XSS"})
        assert response.status_code == 422
        assert error_locations(response) == [["body", "url"]]

    def test_bookmark_read_list_and_delete(self, client: TestClient) -> None:
        for i in range(3):
            client.post("/bookmarks", json={"url": f"https://example.com/{i}", "title": f"B{i}"})
        page = client.get("/bookmarks", params={"limit": 2}).json()
        assert ids(page) == [1, 2] and page["total"] == 3 and page["next_offset"] == 2
        assert client.get("/bookmarks/2").json()["url"] == "https://example.com/1"
        assert client.delete("/bookmarks/2").status_code == 204
        assert client.get("/bookmarks/2").status_code == 404
        assert client.get("/bookmarks/2").json() == {"detail": "bookmark 2 not found"}
        again = client.post("/bookmarks", json={"url": "https://example.com/1", "title": "Back"})
        assert again.status_code == 201, "after a delete the URL can be bookmarked again"

    def test_openapi_info(self, openapi: dict) -> None:
        info = openapi["info"]
        assert info["title"] == "Notes & Bookmarks API" and info["version"] == api.API_VERSION
        assert info.get("description"), "describe the API (pagination and error conventions) in create_app"

    def test_openapi_paths_and_methods(self, openapi: dict) -> None:
        methods = {path: set(ops) for path, ops in openapi["paths"].items()}
        assert methods == {
            "/notes": {"get", "post"},
            "/notes/{note_id}": {"get", "patch", "delete"},
            "/bookmarks": {"get", "post"},
            "/bookmarks/{bookmark_id}": {"get", "delete"},
        }

    def test_openapi_documents_status_codes(self, openapi: dict) -> None:
        paths = openapi["paths"]
        error_ref = "#/components/schemas/ErrorResponse"
        assert {"201", "422"} <= set(paths["/notes"]["post"]["responses"])
        assert "204" in paths["/notes/{note_id}"]["delete"]["responses"]
        for path, method in [
            ("/notes/{note_id}", "get"),
            ("/notes/{note_id}", "patch"),
            ("/bookmarks/{bookmark_id}", "get"),
        ]:
            not_found = paths[path][method]["responses"].get("404")
            assert not_found, f"{method.upper()} {path} should document its 404 response"
            assert not_found["content"]["application/json"]["schema"]["$ref"] == error_ref
        conflict = paths["/bookmarks"]["post"]["responses"].get("409")
        assert conflict and conflict["content"]["application/json"]["schema"]["$ref"] == error_ref

    def test_operation_ids_are_clean_and_unique(self, openapi: dict) -> None:
        operation_ids = [op["operationId"] for ops in openapi["paths"].values() for op in ops.values()]
        assert sorted(operation_ids) == sorted(
            [
                "create_note",
                "list_notes",
                "get_note",
                "update_note",
                "delete_note",
                "create_bookmark",
                "list_bookmarks",
                "get_bookmark",
                "delete_bookmark",
            ]
        ), "use generate_unique_id_function so operationIds are the route function names"

    def test_every_operation_has_a_summary_and_tag(self, openapi: dict) -> None:
        tag_names = {tag["name"]: tag.get("description") for tag in openapi.get("tags", [])}
        assert set(tag_names) == {"notes", "bookmarks"} and all(tag_names.values()), (
            "describe the 'notes' and 'bookmarks' tags with openapi_tags"
        )
        for path, ops in openapi["paths"].items():
            for method, op in ops.items():
                assert op.get("summary"), f"{method.upper()} {path} needs a summary"
                assert len(op.get("tags", [])) == 1 and op["tags"][0] in tag_names

    def test_pagination_parameters_are_documented(self, openapi: dict) -> None:
        params = {p["name"]: p for p in openapi["paths"]["/notes"]["get"]["parameters"]}
        assert set(params) == {"limit", "offset", "tag"}
        assert params["limit"]["schema"]["minimum"] == 1 and params["limit"]["schema"]["maximum"] == 100
        assert params["limit"]["schema"]["default"] == 20

    def test_docs_page_is_served(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200 and "swagger-ui" in response.text.lower()
