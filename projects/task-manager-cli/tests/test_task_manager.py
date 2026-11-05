"""Behaviour tests for the task_manager package, one class per milestone.

Run one milestone with ``python -m pytest -k Milestone1``. Every test is
deterministic: data files live in ``tmp_path`` and "today" is always passed in
(``--today`` on the command line).

Milestones 3 and 4 share ``RepositoryContract``: the same tests run against the JSON
and the SQLite repository, because both must behave identically.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from task_manager import cli, models, storage
from task_manager.cli import format_task_table, main
from task_manager.models import (
    Priority,
    Status,
    Task,
    TaskError,
    due_note,
    filter_tasks,
    normalise_title,
    parse_due,
    sort_tasks,
)
from task_manager.storage import (
    JsonTaskRepository,
    SqliteTaskRepository,
    StorageError,
    TaskNotFoundError,
    TaskRepository,
    open_repository,
)

TODAY = date(2026, 10, 22)


def days(n: int) -> date:
    """A date n days after TODAY (negative for the past)."""
    return TODAY + timedelta(days=n)


def normalised_lines(text: str) -> list[str]:
    """Collapse runs of spaces so tests do not depend on column widths."""
    return [" ".join(line.split()) for line in text.splitlines()]


class TestMilestone1Model:
    """Priority, Status and the immutable, self-validating Task."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("high", Priority.HIGH), (" Low ", Priority.LOW), ("MEDIUM", Priority.MEDIUM)],
    )
    def test_priority_parse(self, text: str, expected: Priority) -> None:
        assert Priority.parse(text) is expected

    @pytest.mark.parametrize("text", ["urgent", "", "3"])
    def test_priority_parse_rejects_unknown(self, text: str) -> None:
        with pytest.raises(TaskError, match="priority"):
            Priority.parse(text)

    def test_priority_values_order_and_labels(self) -> None:
        assert Priority.HIGH.value > Priority.MEDIUM.value > Priority.LOW.value
        assert [p.label for p in Priority] == ["low", "medium", "high"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("todo", Status.TODO), ("In-Progress", Status.IN_PROGRESS), (" done ", Status.DONE)],
    )
    def test_status_parse(self, text: str, expected: Status) -> None:
        assert Status.parse(text) is expected

    def test_status_parse_rejects_unknown(self) -> None:
        with pytest.raises(TaskError, match="status"):
            Status.parse("finished")

    def test_normalise_title(self) -> None:
        assert normalise_title("  Buy   milk \n and eggs ") == "Buy milk and eggs"
        assert normalise_title("x" * 200) == "x" * 200
        with pytest.raises(TaskError, match="empty"):
            normalise_title("   ")
        with pytest.raises(TaskError, match="too long"):
            normalise_title("x" * 201)

    def test_task_defaults_and_title_cleanup(self) -> None:
        task = Task(1, "  Water   the plants ")
        assert task == Task(1, "Water the plants", Priority.MEDIUM, None, Status.TODO)

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"id": 0}, id="id-zero"),
            pytest.param({"id": -3}, id="id-negative"),
            pytest.param({"id": True}, id="id-bool"),
            pytest.param({"id": "1"}, id="id-text"),
            pytest.param({"title": ""}, id="empty-title"),
            pytest.param({"priority": "high"}, id="priority-text"),
            pytest.param({"status": "done"}, id="status-text"),
            pytest.param({"due": "2026-10-30"}, id="due-text"),
            pytest.param({"due": datetime(2026, 10, 30, 9, 0)}, id="due-datetime"),
        ],
    )
    def test_task_rejects_invalid_fields(self, kwargs: dict[str, object]) -> None:
        fields: dict[str, object] = {"id": 1, "title": "Valid", **kwargs}
        with pytest.raises(TaskError):
            Task(**fields)  # type: ignore[arg-type]

    def test_task_is_immutable(self) -> None:
        task = Task(1, "Read")
        with pytest.raises(dataclasses.FrozenInstanceError):
            task.title = "Write"  # type: ignore[misc]

    def test_start_and_complete_return_new_tasks(self) -> None:
        task = Task(1, "Read")
        started = task.start()
        assert started.status is Status.IN_PROGRESS and task.status is Status.TODO
        assert started.complete().status is Status.DONE
        assert task.complete().is_done
        with pytest.raises(TaskError, match="already done"):
            task.complete().start()

    def test_to_dict_and_from_dict_round_trip(self) -> None:
        task = Task(7, "Pay rent", Priority.HIGH, date(2026, 11, 1), Status.IN_PROGRESS)
        data = task.to_dict()
        assert data == {
            "id": 7,
            "title": "Pay rent",
            "priority": "high",
            "due": "2026-11-01",
            "status": "in-progress",
        }
        assert json.loads(json.dumps(data)) == data
        assert Task.from_dict(data) == task
        assert Task.from_dict(Task(8, "No date").to_dict()).due is None

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param({"id": 1, "priority": "low", "status": "todo"}, id="missing-title"),
            pytest.param({"id": 1, "title": "x", "priority": "urgent", "status": "todo"}, id="bad-priority"),
            pytest.param(
                {"id": 1, "title": "x", "priority": "low", "status": "todo", "due": "2026-02-30"},
                id="bad-date",
            ),
            pytest.param(
                {"id": 1, "title": "x", "priority": "low", "status": "todo", "due": "tomorrow"}, id="not-iso"
            ),
            pytest.param({"id": 1, "title": "x", "priority": "low", "status": "later"}, id="bad-status"),
            pytest.param(["not", "a", "mapping"], id="not-a-mapping"),
        ],
    )
    def test_from_dict_rejects_invalid_data(self, data: object) -> None:
        with pytest.raises(TaskError):
            Task.from_dict(data)  # type: ignore[arg-type]


class TestMilestone2Rules:
    """Due dates, overdue checks, sorting and filtering, all relative to an explicit today."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-10-30", date(2026, 10, 30)),
            ("today", TODAY),
            ("Tomorrow", days(1)),
            ("+7", days(7)),
            ("+0", TODAY),
            (" 2026-10-22 ", TODAY),
        ],
    )
    def test_parse_due(self, text: str, expected: date) -> None:
        assert parse_due(text, TODAY) == expected

    def test_parse_due_rejects_the_past(self) -> None:
        with pytest.raises(TaskError, match="in the past"):
            parse_due("2026-10-21", TODAY)

    @pytest.mark.parametrize("text", ["next week", "30/10/2026", "2026-13-01", "+", "-3", "20261030", ""])
    def test_parse_due_rejects_unknown_formats(self, text: str) -> None:
        with pytest.raises(TaskError, match="invalid due date"):
            parse_due(text, TODAY)

    @pytest.mark.parametrize(
        ("task", "expected"),
        [
            pytest.param(Task(1, "t", due=days(-1)), True, id="yesterday"),
            pytest.param(Task(1, "t", due=TODAY), False, id="today"),
            pytest.param(Task(1, "t", due=days(-5), status=Status.DONE), False, id="done"),
            pytest.param(Task(1, "t"), False, id="no-due-date"),
        ],
    )
    def test_is_overdue(self, task: Task, expected: bool) -> None:
        assert task.is_overdue(TODAY) is expected

    @pytest.mark.parametrize(
        ("due", "status", "expected"),
        [
            (days(-1), Status.TODO, "overdue by 1 day"),
            (days(-3), Status.IN_PROGRESS, "overdue by 3 days"),
            (TODAY, Status.TODO, "due today"),
            (days(1), Status.TODO, "due tomorrow"),
            (days(5), Status.TODO, "due in 5 days"),
            (days(-3), Status.DONE, ""),
            (None, Status.TODO, ""),
        ],
    )
    def test_due_note(self, due: date | None, status: Status, expected: str) -> None:
        assert due_note(Task(1, "t", due=due, status=status), TODAY) == expected

    def test_sort_open_first_then_priority_then_due_then_id(self) -> None:
        tasks = [
            Task(1, "done high", Priority.HIGH, days(1), Status.DONE),
            Task(2, "low soon", Priority.LOW, days(1)),
            Task(3, "high no date", Priority.HIGH),
            Task(4, "high later", Priority.HIGH, days(9)),
            Task(5, "high soon", Priority.HIGH, days(2)),
            Task(6, "medium in progress", Priority.MEDIUM, status=Status.IN_PROGRESS),
            Task(7, "high soon too", Priority.HIGH, days(2)),
        ]
        original = list(tasks)
        assert [t.id for t in sort_tasks(tasks)] == [5, 7, 4, 3, 6, 2, 1]
        assert tasks == original, "sort_tasks must return a new list and leave its input alone"

    def test_filter_tasks(self) -> None:
        tasks = [
            Task(1, "a", Priority.HIGH, days(-2)),
            Task(2, "b", Priority.LOW, days(-1), Status.DONE),
            Task(3, "c", Priority.HIGH, days(3), Status.IN_PROGRESS),
            Task(4, "d", Priority.LOW),
        ]
        open_statuses = {Status.TODO, Status.IN_PROGRESS}
        assert [t.id for t in filter_tasks(tasks)] == [1, 2, 3, 4]
        assert [t.id for t in filter_tasks(tasks, statuses=open_statuses)] == [1, 3, 4]
        assert [t.id for t in filter_tasks(tasks, priority=Priority.LOW)] == [2, 4]
        assert [t.id for t in filter_tasks(tasks, overdue_on=TODAY)] == [1]
        assert [t.id for t in filter_tasks(tasks, statuses={Status.DONE}, priority=Priority.HIGH)] == []


class RepositoryContract:
    """Behaviour every TaskRepository must have. Subclasses set ``make`` and ``filename``."""

    make: type[TaskRepository]
    filename: str

    @pytest.fixture
    def repo_path(self, tmp_path: Path) -> Path:
        return tmp_path / self.filename

    @pytest.fixture
    def repo(self, repo_path: Path) -> TaskRepository:
        return self.make(repo_path)

    def test_starts_empty(self, repo: TaskRepository) -> None:
        assert repo.all() == []

    def test_add_assigns_ids_and_returns_the_task(self, repo: TaskRepository) -> None:
        first = repo.add("First")
        second = repo.add("  Second  task ", priority=Priority.HIGH, due=date(2026, 10, 30))
        assert first == Task(1, "First")
        assert second == Task(2, "Second task", Priority.HIGH, date(2026, 10, 30), Status.TODO)
        assert repo.all() == [first, second]

    def test_add_validates_before_storing(self, repo: TaskRepository) -> None:
        with pytest.raises(TaskError):
            repo.add("   ")
        with pytest.raises(TaskError):
            repo.add("ok", priority="high")  # type: ignore[arg-type]
        assert repo.all() == []

    def test_get(self, repo: TaskRepository) -> None:
        task = repo.add("Find me", due=date(2026, 12, 24))
        assert repo.get(task.id) == task
        with pytest.raises(TaskNotFoundError, match="task 99 does not exist"):
            repo.get(99)

    def test_update(self, repo: TaskRepository) -> None:
        task = repo.add("Write report")
        repo.update(task.start())
        assert repo.get(task.id).status is Status.IN_PROGRESS
        with pytest.raises(TaskNotFoundError):
            repo.update(Task(42, "Ghost"))

    def test_delete(self, repo: TaskRepository) -> None:
        keep, remove = repo.add("Keep"), repo.add("Remove")
        assert repo.delete(remove.id) == remove
        assert repo.all() == [keep]
        with pytest.raises(TaskNotFoundError):
            repo.delete(remove.id)

    def test_ids_are_never_reused(self, repo: TaskRepository) -> None:
        repo.add("one")
        two = repo.add("two")
        repo.delete(two.id)
        assert repo.add("three").id == 3

    def test_data_persists_across_repository_objects(self, repo: TaskRepository, repo_path: Path) -> None:
        task = repo.add("Persist me", priority=Priority.LOW, due=date(2027, 1, 1))
        assert self.make(repo_path).all() == [task]

    @pytest.mark.parametrize(
        "title",
        [
            pytest.param("Café ☕ 'single' \"double\"", id="unicode-and-quotes"),
            pytest.param("Robert'); DROP TABLE tasks;--", id="sql-injection"),
        ],
    )
    def test_titles_are_stored_as_plain_text(self, repo: TaskRepository, title: str) -> None:
        task = repo.add(title)
        assert repo.all() == [task]
        assert repo.get(task.id).title == title


class TestMilestone3JsonStorage(RepositoryContract):
    """JsonTaskRepository: a versioned JSON file, saved atomically, validated on load."""

    make = JsonTaskRepository
    filename = "tasks.json"

    def test_reading_does_not_create_the_file(self, repo: TaskRepository, repo_path: Path) -> None:
        assert repo.all() == []
        assert not repo_path.exists()

    def test_file_format(self, repo: TaskRepository, repo_path: Path) -> None:
        repo.add("Pay rent", priority=Priority.HIGH, due=date(2026, 11, 1))
        assert json.loads(repo_path.read_text(encoding="utf-8")) == {
            "version": 1,
            "next_id": 2,
            "tasks": [
                {"id": 1, "title": "Pay rent", "priority": "high", "due": "2026-11-01", "status": "todo"}
            ],
        }

    @pytest.mark.parametrize(
        "content",
        [
            pytest.param("{not json", id="invalid-json"),
            pytest.param("[]", id="wrong-shape"),
            pytest.param('{"version": 2, "next_id": 1, "tasks": []}', id="unknown-version"),
            pytest.param('{"version": 1, "next_id": 2, "tasks": [{"id": 1}]}', id="invalid-task"),
            pytest.param(
                '{"version": 1, "next_id": 3, "tasks": ['
                '{"id": 1, "title": "a", "priority": "low", "status": "todo"},'
                '{"id": 1, "title": "b", "priority": "low", "status": "todo"}]}',
                id="duplicate-ids",
            ),
            pytest.param(
                '{"version": 1, "next_id": 1, "tasks": ['
                '{"id": 1, "title": "a", "priority": "low", "status": "todo"}]}',
                id="next-id-too-small",
            ),
        ],
    )
    def test_invalid_files_raise_storage_error(
        self, repo: TaskRepository, repo_path: Path, content: str
    ) -> None:
        repo_path.write_text(content, encoding="utf-8")
        with pytest.raises(StorageError, match="tasks.json"):
            repo.all()

    def test_corrupt_file_is_never_overwritten(self, repo: TaskRepository, repo_path: Path) -> None:
        repo_path.write_text("{oops", encoding="utf-8")
        with pytest.raises(StorageError):
            repo.add("New task")
        assert repo_path.read_text(encoding="utf-8") == "{oops"

    def test_failed_save_keeps_the_old_file_and_no_temp_files(
        self, repo: TaskRepository, repo_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo.add("Existing")
        before = repo_path.read_bytes()

        def failing_replace(src: str, dst: str) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", failing_replace)
        with pytest.raises(StorageError, match="cannot write"):
            repo.add("Never saved")
        assert repo_path.read_bytes() == before
        assert sorted(p.name for p in repo_path.parent.iterdir()) == ["tasks.json"]


class TestMilestone4SqliteStorage(RepositoryContract):
    """SqliteTaskRepository: the same contract, in a database, with parameterised SQL."""

    make = SqliteTaskRepository
    filename = "tasks.db"

    def test_creates_the_schema(self, repo: TaskRepository, repo_path: Path) -> None:
        with closing(sqlite3.connect(repo_path)) as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        assert "tasks" in tables

    def test_row_layout(self, repo: TaskRepository, repo_path: Path) -> None:
        repo.add("Pay rent", priority=Priority.HIGH, due=date(2026, 11, 1))
        with closing(sqlite3.connect(repo_path)) as conn:
            row = conn.execute("SELECT id, title, priority, due, status FROM tasks").fetchone()
        assert row == (1, "Pay rent", 3, "2026-11-01", "todo"), (
            "priority is stored as its number, due as ISO text"
        )

    def test_a_file_that_is_not_a_database(self, repo_path: Path) -> None:
        repo_path.write_text("this is not SQLite", encoding="utf-8")
        with pytest.raises(StorageError):
            SqliteTaskRepository(repo_path).all()

    def test_sql_is_never_built_from_strings(self) -> None:
        tree = ast.parse(Path(storage.__file__).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ]
        assert calls, "SqliteTaskRepository should call execute()"
        for call in calls:
            first = call.args[0] if call.args else None
            assert isinstance(first, ast.Constant | ast.Name), (
                f"line {call.lineno}: pass SQL as a constant string and the values as ? parameters, "
                "never an f-string, % formatting or .format()"
            )

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("tasks.json", JsonTaskRepository),
            ("tasks.db", SqliteTaskRepository),
            ("TASKS.SQLITE", SqliteTaskRepository),
            ("work.sqlite3", SqliteTaskRepository),
        ],
    )
    def test_open_repository_chooses_by_suffix(self, tmp_path: Path, name: str, expected: type) -> None:
        assert type(open_repository(tmp_path / name)) is expected

    def test_open_repository_rejects_other_suffixes(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="unsupported"):
            open_repository(tmp_path / "tasks.txt")


class TestMilestone5Cli:
    """The argparse front end and the package structure."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> Path:
        return tmp_path / "tasks.json"

    @staticmethod
    def run(
        capsys: pytest.CaptureFixture[str], db: Path, *args: str, today: str = "2026-10-22"
    ) -> tuple[int, str, str]:
        code = main(["--db", str(db), "--today", today, *args])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    def add_sample_tasks(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        for args in (
            ["add", "Submit report", "-p", "high", "--due", "tomorrow"],
            ["add", "Read a book", "--priority", "LOW"],
            ["add", "Fix bike", "--due", "2026-10-25"],
        ):
            assert self.run(capsys, db, *args)[0] == 0

    def test_add_prints_what_was_added(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        code, out, err = self.run(capsys, db, "add", "Submit report", "-p", "high", "--due", "tomorrow")
        assert (code, err) == (0, "")
        assert out.strip() == "Added task 1: Submit report (high, due 2026-10-23)."

    def test_list_sorts_by_priority_then_due_date(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        code, out, _ = self.run(capsys, db, "list")
        assert code == 0
        assert normalised_lines(out) == [
            "ID Priority Status Due Title",
            "1 high todo 2026-10-23 Submit report (due tomorrow)",
            "3 medium todo 2026-10-25 Fix bike (due in 3 days)",
            "2 low todo - Read a book",
            "3 task(s), 0 overdue.",
        ]

    def test_status_changes_and_status_filters(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        assert self.run(capsys, db, "start", "3")[1].strip() == "Started task 3: Fix bike."
        assert self.run(capsys, db, "start", "3")[1].strip() == "Task 3 is already in progress."
        assert self.run(capsys, db, "done", "1")[1].strip() == "Completed task 1: Submit report."
        assert self.run(capsys, db, "done", "1")[1].strip() == "Task 1 is already done."
        open_ids = [line.split()[0] for line in normalised_lines(self.run(capsys, db, "list")[1])[1:-1]]
        assert open_ids == ["3", "2"], "list shows open tasks (todo and in progress) by default"
        done = normalised_lines(self.run(capsys, db, "list", "--status", "done")[1])
        assert done[1].startswith("1 high done")
        assert len(normalised_lines(self.run(capsys, db, "list", "--status", "all")[1])) == 5

    def test_cannot_start_a_done_task(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        self.run(capsys, db, "done", "2")
        code, out, err = self.run(capsys, db, "start", "2")
        assert (code, out) == (1, "")
        assert err.strip() == "error: task 2 is already done"

    def test_overdue_note_and_filter(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        code, out, _ = self.run(capsys, db, "list", "--overdue", today="2026-10-26")
        assert code == 0
        assert normalised_lines(out) == [
            "ID Priority Status Due Title",
            "1 high todo 2026-10-23 Submit report (overdue by 3 days)",
            "3 medium todo 2026-10-25 Fix bike (overdue by 1 day)",
            "2 task(s), 2 overdue.",
        ]

    def test_priority_filter_and_empty_result(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        lines = normalised_lines(self.run(capsys, db, "list", "-p", "low")[1])
        assert lines[1:] == ["2 low todo - Read a book", "1 task(s), 0 overdue."]
        assert self.run(capsys, db, "list", "--status", "done")[1].strip() == "No tasks found."

    def test_delete(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        self.add_sample_tasks(capsys, db)
        assert self.run(capsys, db, "delete", "2")[1].strip() == "Deleted task 2: Read a book."
        assert "Read a book" not in self.run(capsys, db, "list", "--status", "all")[1]
        code, _, err = self.run(capsys, db, "delete", "2")
        assert code == 1 and err.strip() == "error: task 2 does not exist"

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            pytest.param(["add", "   "], "title cannot be empty", id="empty-title"),
            pytest.param(["add", "Late", "--due", "2026-10-01"], "in the past", id="past-due"),
            pytest.param(["add", "Vague", "--due", "someday"], "invalid due date", id="bad-due"),
            pytest.param(["done", "99"], "task 99 does not exist", id="unknown-id"),
        ],
    )
    def test_user_errors_exit_with_1(
        self, capsys: pytest.CaptureFixture[str], db: Path, args: list[str], message: str
    ) -> None:
        code, out, err = self.run(capsys, db, *args)
        assert (code, out) == (1, "")
        assert err.startswith("error: ") and message in err
        assert not db.exists() or JsonTaskRepository(db).all() == [], "nothing may be saved after an error"

    @pytest.mark.parametrize(
        "args",
        [
            pytest.param([], id="no-command"),
            pytest.param(["add"], id="no-title"),
            pytest.param(["add", "x", "-p", "urgent"], id="bad-priority"),
            pytest.param(["done", "abc"], id="id-not-a-number"),
            pytest.param(["list", "--status", "later"], id="bad-status"),
        ],
    )
    def test_usage_errors_exit_with_2(self, db: Path, args: list[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--db", str(db), "--today", "2026-10-22", *args])
        assert excinfo.value.code == 2

    def test_invalid_today_is_a_usage_error(self, db: Path) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--db", str(db), "--today", "22/10/2026", "list"])
        assert excinfo.value.code == 2

    def test_sqlite_backend(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        db = tmp_path / "tasks.db"
        self.add_sample_tasks(capsys, db)
        assert db.read_bytes()[:16] == b"SQLite format 3\x00"
        assert normalised_lines(self.run(capsys, db, "list")[1])[-1] == "3 task(s), 0 overdue."

    def test_corrupt_file_is_reported_and_kept(self, capsys: pytest.CaptureFixture[str], db: Path) -> None:
        db.write_text("{oops", encoding="utf-8")
        code, _, err = self.run(capsys, db, "add", "New")
        assert code == 1 and "is not valid JSON" in err
        assert db.read_text(encoding="utf-8") == "{oops"

    def test_default_data_file_is_in_the_current_folder(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert main(["--today", "2026-10-22", "add", "Here"]) == 0
        assert (tmp_path / "tasks.json").exists()

    def test_format_task_table_handles_no_tasks(self) -> None:
        assert format_task_table([], TODAY) == "No tasks found."

    @staticmethod
    def imports_of(module: ModuleType) -> set[str]:
        tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add("." * node.level + (node.module or ""))
        return names

    def test_models_depend_on_nothing_else_in_the_package(self) -> None:
        forbidden = {
            "json",
            "sqlite3",
            "argparse",
            ".storage",
            ".cli",
            "task_manager.storage",
            "task_manager.cli",
        }
        assert not self.imports_of(models) & forbidden, "models must not know about storage or the CLI"

    def test_storage_does_not_depend_on_the_cli(self) -> None:
        assert not self.imports_of(storage) & {"argparse", ".cli", "task_manager.cli"}
        assert ".models" in self.imports_of(storage) or "task_manager.models" in self.imports_of(storage)
        assert ".storage" in self.imports_of(cli) or "task_manager.storage" in self.imports_of(cli)

    def test_only_the_cli_prints(self) -> None:
        for module in (models, storage):
            tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
            prints = [
                n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print"
            ]
            assert not prints, f"{module.__name__} should return values; only cli.py prints"

    def test_python_dash_m_entry_point_exists(self) -> None:
        assert importlib.util.find_spec("task_manager.__main__") is not None
