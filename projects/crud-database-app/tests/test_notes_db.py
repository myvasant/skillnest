"""Behaviour tests for the SQLite notes app, grouped by milestone.

Run one milestone with:  python -m pytest -k Milestone1
Every test uses a fresh database file under pytest's ``tmp_path``.
"""

import ast
import hashlib
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import notes_db
import pytest
from fastapi.testclient import TestClient


class FakeClock:
    """A controllable clock: tests move time forward instead of sleeping."""

    def __init__(self, start: datetime = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "notes.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = notes_db.connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def migrated(conn: sqlite3.Connection, clock: FakeClock) -> sqlite3.Connection:
    """A connection to a database with the project's real migrations applied."""
    notes_db.apply_migrations(conn, notes_db.MIGRATIONS_DIR, clock=clock)
    return conn


@pytest.fixture
def repo(migrated: sqlite3.Connection, clock: FakeClock) -> notes_db.SqliteNoteRepository:
    return notes_db.SqliteNoteRepository(migrated, clock)


@pytest.fixture
def client(db_path: Path, clock: FakeClock) -> Iterator[TestClient]:
    # The `with` block runs the app's startup (lifespan), which applies the migrations.
    with TestClient(notes_db.create_app(db_path, clock=clock)) as test_client:
        yield test_client


@contextmanager
def other_connection(db_path: Path, timeout: float = 5.0) -> Iterator[sqlite3.Connection]:
    """A second, independent connection (what another request or process would see), closed afterwards.

    Note: ``with sqlite3.connect(...)`` would NOT close the connection; it only commits or rolls back.
    """
    connection = sqlite3.connect(db_path, isolation_level=None, timeout=timeout)
    try:
        yield connection
    finally:
        connection.close()


def write_migrations(directory: Path, files: dict[str, str]) -> Path:
    """Create a migrations folder for a test."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, sql in files.items():
        (directory / name).write_text(sql, encoding="utf-8")
    return directory


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def count(conn: sqlite3.Connection, table: str) -> int:
    queries = {
        "notes": "SELECT COUNT(*) FROM notes",
        "tags": "SELECT COUNT(*) FROM tags",
        "note_tags": "SELECT COUNT(*) FROM note_tags",
        "items": "SELECT COUNT(*) FROM items",
    }
    return conn.execute(queries[table]).fetchone()[0]


def insert_note(conn: sqlite3.Connection, title: str = "A note") -> int:
    """Insert a row directly with SQL (bypassing the repository) and return its id."""
    stamp = "2026-01-01T09:00:00.000000+00:00"
    cursor = conn.execute(
        "INSERT INTO notes (title, body, created_at, updated_at) VALUES (?, '', ?, ?)", (title, stamp, stamp)
    )
    return cursor.lastrowid


def make(repo: notes_db.SqliteNoteRepository, title: str = "A note", **fields) -> notes_db.Note:
    return repo.add(notes_db.NoteCreate(title=title, **fields))


# ---------------------------------------------------------------------------
# Milestone 1: connections and transactions
# ---------------------------------------------------------------------------


class TestMilestone1ConnectionAndTransactions:
    def test_foreign_keys_are_enforced(self, conn: sqlite3.Connection) -> None:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1, (
            "connect() must run PRAGMA foreign_keys = ON; SQLite ignores REFERENCES constraints otherwise"
        )

    def test_rows_can_be_read_by_column_name(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT 42 AS answer").fetchone()
        assert row["answer"] == 42, "set conn.row_factory = sqlite3.Row so rows can be read by column name"

    def test_connection_is_in_autocommit_mode(self, conn: sqlite3.Connection, db_path: Path) -> None:
        assert conn.isolation_level is None, "open the connection with isolation_level=None (autocommit)"
        conn.execute("CREATE TABLE items (name TEXT)")
        conn.execute("INSERT INTO items (name) VALUES (?)", ("visible",))
        assert not conn.in_transaction, "outside transaction() no transaction should be left open"
        with other_connection(db_path) as other:
            assert other.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1

    def test_file_databases_use_write_ahead_logging(self, conn: sqlite3.Connection) -> None:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal", f"run PRAGMA journal_mode = WAL for file databases, got {mode!r}"

    def test_transaction_commits_when_the_block_succeeds(
        self, conn: sqlite3.Connection, db_path: Path
    ) -> None:
        conn.execute("CREATE TABLE items (name TEXT)")
        with notes_db.transaction(conn):
            conn.execute("INSERT INTO items (name) VALUES (?)", ("a",))
            conn.execute("INSERT INTO items (name) VALUES (?)", ("b",))
        assert not conn.in_transaction, "transaction() must COMMIT when the block finishes"
        with other_connection(db_path) as other:
            assert other.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2

    def test_transaction_rolls_back_and_reraises(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE items (name TEXT)")
        with pytest.raises(ZeroDivisionError):
            with notes_db.transaction(conn):
                conn.execute("INSERT INTO items (name) VALUES (?)", ("half-done",))
                _ = 1 / 0
        assert not conn.in_transaction, "transaction() must ROLLBACK when the block raises"
        assert count(conn, "items") == 0, "the insert made before the error must be rolled back"

    def test_transaction_takes_the_write_lock_immediately(
        self, conn: sqlite3.Connection, db_path: Path
    ) -> None:
        conn.execute("CREATE TABLE items (name TEXT)")
        with other_connection(db_path, timeout=0) as impatient, notes_db.transaction(conn):
            # No write has happened yet, but BEGIN IMMEDIATE already holds the write lock.
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                impatient.execute("BEGIN IMMEDIATE")

    def test_nested_transactions_are_rejected(self, conn: sqlite3.Connection) -> None:
        with notes_db.transaction(conn):
            with pytest.raises(RuntimeError, match="nested"):
                with notes_db.transaction(conn):
                    pass


# ---------------------------------------------------------------------------
# Milestone 2: the migration runner
# ---------------------------------------------------------------------------

CREATE_ITEMS = "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
ADD_PRICE = "ALTER TABLE items ADD COLUMN price INTEGER NOT NULL DEFAULT 0;\n"
CREATE_LOGS = "CREATE TABLE logs (message TEXT);\n"


class TestMilestone2MigrationRunner:
    def test_discovers_migrations_in_numeric_order(self, tmp_path: Path) -> None:
        folder = write_migrations(
            tmp_path / "m",
            {
                "0003_create_logs.sql": CREATE_LOGS,
                "0001_create_items.sql": CREATE_ITEMS,
                "0002_add_price.sql": ADD_PRICE,
            },
        )
        migrations = notes_db.discover_migrations(folder)
        assert [m.version for m in migrations] == [1, 2, 3]
        assert [m.name for m in migrations] == ["create_items", "add_price", "create_logs"]
        assert migrations[0].sql == CREATE_ITEMS
        assert migrations[1].checksum == hashlib.sha256(ADD_PRICE.encode("utf-8")).hexdigest(), (
            "checksum should be the SHA-256 hex digest of the file's text"
        )

    def test_ignores_files_that_are_not_sql(self, tmp_path: Path) -> None:
        folder = write_migrations(
            tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS, "README.md": "# notes"}
        )
        assert [m.version for m in notes_db.discover_migrations(folder)] == [1]

    @pytest.mark.parametrize(
        "bad_name", ["1_create_items.sql", "0001-create-items.sql", "0001_CreateItems.sql"]
    )
    def test_rejects_badly_named_sql_files(self, tmp_path: Path, bad_name: str) -> None:
        folder = write_migrations(tmp_path / "m", {bad_name: CREATE_ITEMS})
        with pytest.raises(notes_db.MigrationError, match=re.escape(bad_name)):
            notes_db.discover_migrations(folder)

    def test_rejects_duplicate_numbers(self, tmp_path: Path) -> None:
        folder = write_migrations(
            tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS, "0001_create_logs.sql": CREATE_LOGS}
        )
        with pytest.raises(notes_db.MigrationError, match="0001"):
            notes_db.discover_migrations(folder)

    def test_rejects_gaps_in_the_numbering(self, tmp_path: Path) -> None:
        folder = write_migrations(
            tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS, "0003_create_logs.sql": CREATE_LOGS}
        )
        with pytest.raises(notes_db.MigrationError, match="0002"):
            notes_db.discover_migrations(folder)

    def test_applies_migrations_in_order_and_records_them(
        self, tmp_path: Path, conn: sqlite3.Connection, clock: FakeClock
    ) -> None:
        # 0002 alters the table 0001 creates, so it only works if they run in order.
        folder = write_migrations(
            tmp_path / "m", {"0002_add_price.sql": ADD_PRICE, "0001_create_items.sql": CREATE_ITEMS}
        )
        assert notes_db.apply_migrations(conn, folder, clock=clock) == [1, 2]
        conn.execute("INSERT INTO items (name, price) VALUES (?, ?)", ("pen", 120))
        rows = conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [(1, "create_items"), (2, "add_price")]
        assert rows[0][2] == hashlib.sha256(CREATE_ITEMS.encode("utf-8")).hexdigest()
        assert rows[0][3].startswith("2026-01-01T09:00:00"), "applied_at should come from the injected clock"

    def test_running_twice_applies_nothing_the_second_time(
        self, tmp_path: Path, conn: sqlite3.Connection
    ) -> None:
        folder = write_migrations(tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS})
        notes_db.apply_migrations(conn, folder)
        assert notes_db.apply_migrations(conn, folder) == [], "already-applied migrations must be skipped"
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1

    def test_only_new_migrations_are_applied(self, tmp_path: Path, conn: sqlite3.Connection) -> None:
        folder = write_migrations(tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS})
        notes_db.apply_migrations(conn, folder)
        write_migrations(folder, {"0002_add_price.sql": ADD_PRICE})
        assert notes_db.apply_migrations(conn, folder) == [2]
        assert notes_db.schema_version(conn) == 2

    def test_a_failing_migration_leaves_nothing_behind(
        self, tmp_path: Path, conn: sqlite3.Connection
    ) -> None:
        broken = "CREATE TABLE half_done (id INTEGER);\nINSERT INTO no_such_table VALUES (1);\n"
        folder = write_migrations(
            tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS, "0002_broken.sql": broken}
        )
        with pytest.raises(notes_db.MigrationError, match="0002_broken.sql"):
            notes_db.apply_migrations(conn, folder)
        assert "half_done" not in table_names(conn), (
            "the CREATE TABLE before the failing statement must be rolled back with the rest of the migration"
        )
        assert "items" in table_names(conn), "migration 0001 succeeded and must stay applied"
        assert notes_db.schema_version(conn) == 1, "a failed migration must not be recorded"
        assert not conn.in_transaction

    def test_a_fixed_migration_can_be_applied_after_a_failure(
        self, tmp_path: Path, conn: sqlite3.Connection
    ) -> None:
        folder = write_migrations(tmp_path / "m", {"0001_create_items.sql": "CREATE TABLE items (;\n"})
        with pytest.raises(notes_db.MigrationError):
            notes_db.apply_migrations(conn, folder)
        write_migrations(folder, {"0001_create_items.sql": CREATE_ITEMS})
        assert notes_db.apply_migrations(conn, folder) == [1]

    def test_editing_an_applied_migration_is_detected(self, tmp_path: Path, conn: sqlite3.Connection) -> None:
        folder = write_migrations(tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS})
        notes_db.apply_migrations(conn, folder)
        write_migrations(
            folder,
            {"0001_create_items.sql": CREATE_ITEMS + "-- edited\n", "0002_create_logs.sql": CREATE_LOGS},
        )
        with pytest.raises(notes_db.MigrationError, match="0001_create_items.sql"):
            notes_db.apply_migrations(conn, folder)
        assert "logs" not in table_names(conn), "check the whole history before applying anything new"

    def test_a_database_newer_than_the_code_is_detected(
        self, tmp_path: Path, conn: sqlite3.Connection
    ) -> None:
        folder = write_migrations(
            tmp_path / "m", {"0001_create_items.sql": CREATE_ITEMS, "0002_add_price.sql": ADD_PRICE}
        )
        notes_db.apply_migrations(conn, folder)
        (folder / "0002_add_price.sql").unlink()
        with pytest.raises(notes_db.MigrationError, match="2"):
            notes_db.apply_migrations(conn, folder)

    def test_schema_version_of_a_new_database_is_zero(self, conn: sqlite3.Connection) -> None:
        assert notes_db.schema_version(conn) == 0


# ---------------------------------------------------------------------------
# Milestone 3: the schema (migrations/0002 and 0003)
# ---------------------------------------------------------------------------


class TestMilestone3Schema:
    def test_the_project_ships_three_numbered_migrations(self) -> None:
        versions = [m.version for m in notes_db.discover_migrations(notes_db.MIGRATIONS_DIR)]
        assert versions == [1, 2, 3]

    def test_migrations_create_the_tables(self, migrated: sqlite3.Connection) -> None:
        expected = {"notes", "tags", "note_tags", "schema_migrations"}
        missing = expected - table_names(migrated)
        assert not missing, f"tables missing after apply_migrations: {sorted(missing)}"
        assert notes_db.schema_version(migrated) == 3

    def test_note_tags_has_the_expected_columns(self, migrated: sqlite3.Connection) -> None:
        columns = {row["name"] for row in migrated.execute("PRAGMA table_info(note_tags)")}
        assert {"note_id", "tag_id", "position"} <= columns, f"note_tags columns are {sorted(columns)}"

    def test_tag_names_are_unique(self, migrated: sqlite3.Connection) -> None:
        migrated.execute("INSERT INTO tags (name) VALUES (?)", ("python",))
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute("INSERT INTO tags (name) VALUES (?)", ("python",))

    @pytest.mark.parametrize("title", ["", "x" * 201])
    def test_the_title_check_constraint_rejects_bad_titles(
        self, migrated: sqlite3.Connection, title: str
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            insert_note(migrated, title)

    def test_links_to_missing_notes_are_rejected(self, migrated: sqlite3.Connection) -> None:
        migrated.execute("INSERT INTO tags (id, name) VALUES (?, ?)", (1, "python"))
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO note_tags (note_id, tag_id, position) VALUES (?, ?, ?)", (999, 1, 0)
            )

    def test_a_note_cannot_have_the_same_tag_twice(self, migrated: sqlite3.Connection) -> None:
        note_id = insert_note(migrated)
        migrated.execute("INSERT INTO tags (id, name) VALUES (?, ?)", (1, "python"))
        migrated.execute(
            "INSERT INTO note_tags (note_id, tag_id, position) VALUES (?, ?, ?)", (note_id, 1, 0)
        )
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO note_tags (note_id, tag_id, position) VALUES (?, ?, ?)", (note_id, 1, 1)
            )

    def test_deleting_a_note_cascades_to_its_links(self, migrated: sqlite3.Connection) -> None:
        note_id = insert_note(migrated)
        migrated.execute("INSERT INTO tags (id, name) VALUES (?, ?)", (1, "python"))
        migrated.execute(
            "INSERT INTO note_tags (note_id, tag_id, position) VALUES (?, ?, ?)", (note_id, 1, 0)
        )
        migrated.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        assert count(migrated, "note_tags") == 0, (
            "note_tags.note_id needs REFERENCES notes (id) ON DELETE CASCADE"
        )
        assert count(migrated, "tags") == 1, "the tag itself stays; only the link goes"

    def test_finding_notes_by_tag_uses_an_index(self, migrated: sqlite3.Connection) -> None:
        plan = migrated.execute(
            "EXPLAIN QUERY PLAN SELECT note_id FROM note_tags WHERE tag_id = ?", (1,)
        ).fetchall()
        details = " | ".join(row[-1] for row in plan)
        assert "SEARCH" in details, (
            f"looking up note_tags by tag_id scans the whole table ({details}); "
            "add CREATE INDEX ... ON note_tags (tag_id) in 0003_add_indexes.sql"
        )

    def test_ids_are_never_reused(self, migrated: sqlite3.Connection) -> None:
        first = insert_note(migrated, "first")
        migrated.execute("DELETE FROM notes WHERE id = ?", (first,))
        assert insert_note(migrated, "second") == first + 1, "notes.id should use AUTOINCREMENT"


# ---------------------------------------------------------------------------
# Milestone 4: the repository
# ---------------------------------------------------------------------------


class TagsFail(notes_db.SqliteNoteRepository):
    """A repository whose tag step fails half-way through a write, like a crash or a full disk."""

    def _set_tags(self, note_id: int, tags: Sequence[str]) -> None:
        raise RuntimeError("disk full while saving tags")


class TestMilestone4Repository:
    def test_implements_the_repository_interface(self, repo: notes_db.SqliteNoteRepository) -> None:
        assert isinstance(repo, notes_db.NoteRepository)

    def test_add_returns_the_stored_note(self, repo: notes_db.SqliteNoteRepository, clock: FakeClock) -> None:
        note = make(repo, "Read the SQLite docs", body="Section on WAL", tags=["Databases", "to-read"])
        assert note.id == 1
        assert (note.title, note.body, note.tags) == (
            "Read the SQLite docs",
            "Section on WAL",
            ["databases", "to-read"],
        )
        assert note.created_at == clock.now and note.updated_at == clock.now

    def test_notes_persist_across_connections(
        self, repo: notes_db.SqliteNoteRepository, db_path: Path, clock: FakeClock
    ) -> None:
        note = make(repo, "Persist me", tags=["keep"])
        fresh = notes_db.connect(db_path)
        try:
            assert notes_db.SqliteNoteRepository(fresh, clock).get(note.id) == note
        finally:
            fresh.close()

    def test_tags_keep_the_order_they_were_given_in(self, repo: notes_db.SqliteNoteRepository) -> None:
        note = make(repo, tags=["zeta", "alpha", "mid"])
        assert repo.get(note.id).tags == ["zeta", "alpha", "mid"]

    def test_get_returns_none_for_a_missing_note(self, repo: notes_db.SqliteNoteRepository) -> None:
        assert repo.get(42) is None

    def test_page_orders_by_id_and_counts_all_matches(self, repo: notes_db.SqliteNoteRepository) -> None:
        for number in range(1, 6):
            make(repo, f"note {number}")
        items, total = repo.page(offset=1, limit=2)
        assert [note.id for note in items] == [2, 3]
        assert total == 5

    def test_a_page_past_the_end_is_empty(self, repo: notes_db.SqliteNoteRepository) -> None:
        make(repo)
        assert repo.page(offset=10, limit=5) == ([], 1)

    def test_page_filters_by_tag(self, repo: notes_db.SqliteNoteRepository) -> None:
        make(repo, "a", tags=["python"])
        make(repo, "b", tags=["sql"])
        make(repo, "c", tags=["sql", "python"])
        items, total = repo.page(offset=0, limit=10, tag="python")
        assert ([note.title for note in items], total) == (["a", "c"], 2)
        assert repo.page(offset=0, limit=10, tag="python")[0][1].tags == ["sql", "python"], (
            "filtered notes must still come back with ALL their tags"
        )

    def test_page_rejects_impossible_bounds(self, repo: notes_db.SqliteNoteRepository) -> None:
        with pytest.raises(ValueError):
            repo.page(offset=0, limit=0)
        with pytest.raises(ValueError):
            repo.page(offset=-1, limit=10)

    def test_update_changes_only_the_fields_sent(
        self, repo: notes_db.SqliteNoteRepository, clock: FakeClock
    ) -> None:
        note = make(repo, "Old title", body="Keep this body", tags=["keep"])
        clock.advance(60)
        updated = repo.update(note.id, notes_db.NoteUpdate(title="New title"))
        assert (updated.title, updated.body, updated.tags) == ("New title", "Keep this body", ["keep"])
        assert updated.created_at == note.created_at, "created_at must never change"
        assert updated.updated_at == note.created_at + timedelta(seconds=60), (
            "updated_at comes from the clock"
        )
        assert repo.get(note.id) == updated, "the change must be saved, not just returned"

    def test_update_replaces_the_tags(
        self, repo: notes_db.SqliteNoteRepository, migrated: sqlite3.Connection
    ) -> None:
        note = make(repo, tags=["a", "b"])
        assert repo.update(note.id, notes_db.NoteUpdate(tags=["c"])).tags == ["c"]
        assert count(migrated, "note_tags") == 1, "old links must be removed when tags are replaced"

    def test_update_of_a_missing_note_returns_none(self, repo: notes_db.SqliteNoteRepository) -> None:
        assert repo.update(42, notes_db.NoteUpdate(title="x")) is None

    def test_delete_removes_the_note_and_its_links(
        self, repo: notes_db.SqliteNoteRepository, migrated: sqlite3.Connection
    ) -> None:
        note = make(repo, tags=["a", "b"])
        assert repo.delete(note.id) is True
        assert repo.get(note.id) is None
        assert count(migrated, "note_tags") == 0
        assert repo.delete(note.id) is False, "deleting twice should report that nothing was deleted"

    def test_add_is_all_or_nothing(self, migrated: sqlite3.Connection, clock: FakeClock) -> None:
        with pytest.raises(RuntimeError):
            TagsFail(migrated, clock).add(notes_db.NoteCreate(title="never saved", tags=["x"]))
        assert count(migrated, "notes") == 0, "the note row must be rolled back when saving its tags fails"
        assert not migrated.in_transaction

    def test_update_is_all_or_nothing(self, migrated: sqlite3.Connection, clock: FakeClock) -> None:
        note = notes_db.SqliteNoteRepository(migrated, clock).add(notes_db.NoteCreate(title="original"))
        with pytest.raises(RuntimeError):
            TagsFail(migrated, clock).update(note.id, notes_db.NoteUpdate(title="changed", tags=["x"]))
        assert notes_db.SqliteNoteRepository(migrated, clock).get(note.id).title == "original"

    def test_sql_in_the_data_is_stored_as_plain_text(
        self, repo: notes_db.SqliteNoteRepository, migrated: sqlite3.Connection
    ) -> None:
        nasty = "Robert'); DROP TABLE notes; --"
        note = make(repo, nasty, body="' OR '1'='1")
        assert repo.get(note.id).title == nasty
        assert "notes" in table_names(migrated), "user input must never be executed as SQL"

    def test_sql_in_the_tag_filter_matches_nothing(self, repo: notes_db.SqliteNoteRepository) -> None:
        make(repo, tags=["python"])
        assert repo.page(offset=0, limit=10, tag="' OR 1=1 --") == ([], 0)

    def test_no_sql_is_built_with_string_formatting(self) -> None:
        tree = ast.parse(Path(notes_db.__file__).read_text(encoding="utf-8"))
        sql_words = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE|VALUES)\b", re.IGNORECASE)
        problems = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"execute", "executemany", "executescript"} and node.args:
                    sql = node.args[0]
                    formatted = (
                        isinstance(sql, ast.JoinedStr)
                        or (isinstance(sql, ast.BinOp) and isinstance(sql.op, ast.Mod))
                        or (
                            isinstance(sql, ast.Call)
                            and isinstance(sql.func, ast.Attribute)
                            and sql.func.attr == "format"
                        )
                    )
                    if formatted:
                        problems.append(f"line {node.lineno}: {node.func.attr}() gets a formatted string")
            if isinstance(node, ast.JoinedStr):
                text = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
                if sql_words.search(text) and re.search(r"\b(FROM|INTO|SET)\b", text, re.IGNORECASE):
                    problems.append(f"line {node.lineno}: an f-string that looks like SQL")
        assert not problems, "use ? placeholders and pass values separately:\n" + "\n".join(problems)


# ---------------------------------------------------------------------------
# Milestone 5: the API on SQLite
# ---------------------------------------------------------------------------


def post_note(client: TestClient, title: str = "A note", **fields):
    return client.post("/notes", json={"title": title, **fields})


class TestMilestone5Api:
    def test_startup_applies_the_migrations(self, client: TestClient, db_path: Path) -> None:
        with other_connection(db_path) as other:
            assert notes_db.schema_version(other) == 3, "create_app's lifespan should call apply_migrations"

    def test_create_returns_201_with_a_location(self, client: TestClient) -> None:
        response = post_note(client, "Hello", tags=["Greeting"])
        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["id"], body["title"], body["tags"]) == (1, "Hello", ["greeting"])
        assert response.headers["location"].endswith("/notes/1")

    def test_get_returns_the_note_or_404(self, client: TestClient) -> None:
        note_id = post_note(client, "Find me").json()["id"]
        assert client.get(f"/notes/{note_id}").json()["title"] == "Find me"
        missing = client.get("/notes/42")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "note 42 not found"}

    @pytest.mark.parametrize(
        "payload", [{"title": ""}, {"title": "ok", "colour": "red"}, {"title": "ok", "tags": ["no spaces"]}]
    )
    def test_invalid_notes_are_rejected_with_422(self, client: TestClient, payload: dict) -> None:
        assert client.post("/notes", json=payload).status_code == 422

    def test_list_returns_a_page_and_the_next_offset(self, client: TestClient) -> None:
        for number in range(5):
            post_note(client, f"note {number}")
        first = client.get("/notes", params={"limit": 2}).json()
        assert [item["id"] for item in first["items"]] == [1, 2]
        assert (first["total"], first["limit"], first["offset"], first["next_offset"]) == (5, 2, 0, 2)
        last = client.get("/notes", params={"limit": 2, "offset": 4}).json()
        assert ([item["id"] for item in last["items"]], last["next_offset"]) == ([5], None)

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "ten"}])
    def test_bad_paging_parameters_are_422(self, client: TestClient, params: dict) -> None:
        assert client.get("/notes", params=params).status_code == 422

    def test_list_filters_by_tag_case_insensitively(self, client: TestClient) -> None:
        post_note(client, "a", tags=["python"])
        post_note(client, "b", tags=["sql"])
        page = client.get("/notes", params={"tag": "Python"}).json()
        assert ([item["title"] for item in page["items"]], page["total"]) == (["a"], 1)

    def test_patch_updates_validates_and_404s(self, client: TestClient) -> None:
        note_id = post_note(client, "Draft", body="text").json()["id"]
        response = client.patch(f"/notes/{note_id}", json={"title": "Final"})
        assert response.status_code == 200
        assert (response.json()["title"], response.json()["body"]) == ("Final", "text")
        assert client.patch(f"/notes/{note_id}", json={}).status_code == 422, (
            "an empty PATCH is a client error"
        )
        assert client.patch(f"/notes/{note_id}", json={"title": None}).status_code == 422
        assert client.patch("/notes/42", json={"title": "x"}).status_code == 404

    def test_delete_returns_204_then_404(self, client: TestClient) -> None:
        note_id = post_note(client).json()["id"]
        response = client.delete(f"/notes/{note_id}")
        assert response.status_code == 204 and response.content == b""
        assert client.get(f"/notes/{note_id}").status_code == 404
        assert client.delete(f"/notes/{note_id}").status_code == 404

    def test_notes_survive_a_restart(self, db_path: Path, clock: FakeClock) -> None:
        with TestClient(notes_db.create_app(db_path, clock=clock)) as first_run:
            note_id = post_note(first_run, "Still here?", tags=["persisted"]).json()["id"]
        with TestClient(notes_db.create_app(db_path, clock=clock)) as second_run:
            response = second_run.get(f"/notes/{note_id}")
        assert response.status_code == 200, "the note should be read back from the database file"
        assert response.json()["tags"] == ["persisted"]

    def test_each_request_gets_its_own_connection_and_closes_it(
        self, db_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opened: list[sqlite3.Connection] = []
        real_connect = notes_db.connect

        def spy(path: Path | str) -> sqlite3.Connection:
            connection = real_connect(path)
            opened.append(connection)
            return connection

        monkeypatch.setattr(notes_db, "connect", spy)
        with TestClient(notes_db.create_app(db_path, clock=clock)) as client:
            before = len(opened)
            post_note(client)
            client.get("/notes")
            assert len(opened) == before + 2, "open one connection per request (in a yield dependency)"
        for connection in opened:
            with pytest.raises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")  # raises only if the connection was closed

    def test_app_from_env_reads_the_database_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NOTES_DB_PATH", str(tmp_path / "from-env.db"))
        with TestClient(notes_db.app_from_env()) as client:
            assert post_note(client).status_code == 201
        assert (tmp_path / "from-env.db").exists()
