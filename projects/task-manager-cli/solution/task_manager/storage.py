"""Persistence: one repository interface, two interchangeable back ends.

* :class:`JsonTaskRepository` keeps everything in one versioned JSON file and saves it
  atomically (temporary file + ``os.replace``).
* :class:`SqliteTaskRepository` uses the standard-library ``sqlite3`` module with
  parameterised queries only.

Both raise :class:`TaskNotFoundError` for unknown ids and :class:`StorageError` for
unreadable or invalid data, and both pass the same contract tests. This module depends
on :mod:`task_manager.models` but never on the command line.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from .models import Priority, Status, Task, TaskError

FORMAT_VERSION = 1
SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


class StorageError(Exception):
    """The data file cannot be read or written, or its content is invalid."""


class TaskNotFoundError(LookupError):
    """No task has the requested id."""

    def __init__(self, task_id: int) -> None:
        super().__init__(f"task {task_id} does not exist")
        self.task_id = task_id


class TaskRepository(ABC):
    """Where tasks live. Every implementation must behave exactly the same."""

    @abstractmethod
    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        """Store a new TODO task under a new id (ids are never reused) and return it."""

    @abstractmethod
    def get(self, task_id: int) -> Task:
        """Return the task with this id, or raise TaskNotFoundError."""

    @abstractmethod
    def all(self) -> list[Task]:
        """Return every task in id order."""

    @abstractmethod
    def update(self, task: Task) -> None:
        """Replace the stored task with the same id, or raise TaskNotFoundError."""

    @abstractmethod
    def delete(self, task_id: int) -> Task:
        """Remove the task with this id and return it, or raise TaskNotFoundError."""


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` so that readers see the old or the new file, never half.

    The temporary file is created in the same folder because ``os.replace`` is only
    atomic within one file system. On failure the temporary file is removed.
    """
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


class JsonTaskRepository(TaskRepository):
    """Tasks in a JSON document: ``{"version": 1, "next_id": 4, "tasks": [...]}``."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        next_id, tasks = self._load()
        task = Task(id=next_id, title=title, priority=priority, due=due)
        self._save(next_id + 1, [*tasks, task])
        return task

    def get(self, task_id: int) -> Task:
        _, tasks = self._load()
        return tasks[self._index_of(tasks, task_id)]

    def all(self) -> list[Task]:
        _, tasks = self._load()
        return sorted(tasks, key=lambda task: task.id)

    def update(self, task: Task) -> None:
        next_id, tasks = self._load()
        tasks[self._index_of(tasks, task.id)] = task
        self._save(next_id, tasks)

    def delete(self, task_id: int) -> Task:
        next_id, tasks = self._load()
        removed = tasks.pop(self._index_of(tasks, task_id))
        self._save(next_id, tasks)
        return removed

    @staticmethod
    def _index_of(tasks: list[Task], task_id: int) -> int:
        for index, task in enumerate(tasks):
            if task.id == task_id:
                return index
        raise TaskNotFoundError(task_id)

    def _load(self) -> tuple[int, list[Task]]:
        """Return ``(next_id, tasks)``; a missing file means no tasks yet."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return 1, []
        except (OSError, UnicodeDecodeError) as exc:
            raise StorageError(f"cannot read {self.path}: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StorageError(
                f"{self.path} is not valid JSON (line {exc.lineno}, column {exc.colno})"
            ) from None
        if (
            not isinstance(data, dict)
            or data.get("version") != FORMAT_VERSION
            or not isinstance(data.get("tasks"), list)
        ):
            raise StorageError(f"{self.path} is not a version {FORMAT_VERSION} task file")
        tasks: list[Task] = []
        for number, item in enumerate(data["tasks"], start=1):
            try:
                tasks.append(Task.from_dict(item))
            except TaskError as exc:
                raise StorageError(f"{self.path}: task #{number} is invalid: {exc}") from None
        ids = [task.id for task in tasks]
        if len(set(ids)) != len(ids):
            raise StorageError(f"{self.path}: two tasks share the same id")
        next_id = data.get("next_id")
        if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id <= max(ids, default=0):
            raise StorageError(f"{self.path}: next_id must be a whole number greater than every task id")
        return next_id, tasks

    def _save(self, next_id: int, tasks: list[Task]) -> None:
        payload = {
            "version": FORMAT_VERSION,
            "next_id": next_id,
            "tasks": [task.to_dict() for task in sorted(tasks, key=lambda task: task.id)],
        }
        try:
            atomic_write_text(self.path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise StorageError(f"cannot write {self.path}: {exc.strerror or exc}") from exc


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT    NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    priority INTEGER NOT NULL CHECK (priority IN (1, 2, 3)),
    due      TEXT,
    status   TEXT    NOT NULL CHECK (status IN ('todo', 'in-progress', 'done'))
)
"""


class SqliteTaskRepository(TaskRepository):
    """Tasks in an SQLite database file (created on first use).

    Every query uses ``?`` placeholders, so titles are always data, never SQL.
    ``AUTOINCREMENT`` guarantees that ids of deleted tasks are not reused.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection; commit on success, roll back on error, always close."""
        try:
            conn = sqlite3.connect(self.path)
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open database {self.path}: {exc}") from exc
        try:
            with conn:  # a transaction: commits, or rolls back if the block raises
                yield conn
        except sqlite3.DatabaseError as exc:  # includes "file is not a database"
            raise StorageError(f"database error in {self.path}: {exc}") from exc
        finally:
            conn.close()

    def _row_to_task(self, row: tuple[Any, ...]) -> Task:
        task_id, title, priority, due, status = row
        try:
            return Task(
                id=task_id,
                title=title,
                priority=Priority(priority),
                due=None if due is None else date.fromisoformat(due),
                status=Status(status),
            )
        except (TaskError, ValueError) as exc:
            raise StorageError(f"{self.path}: task {task_id} is invalid: {exc}") from None

    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        # Validate with a placeholder id first, so invalid input never reaches the database.
        draft = Task(id=1, title=title, priority=priority, due=due)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (title, priority, due, status) VALUES (?, ?, ?, ?)",
                (draft.title, draft.priority.value, _iso(draft.due), draft.status.value),
            )
            new_id = cursor.lastrowid
        if new_id is None:
            raise StorageError(f"{self.path}: the database did not return an id for the new task")
        return replace(draft, id=new_id)

    def get(self, task_id: int) -> Task:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, priority, due, status FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise TaskNotFoundError(task_id)
        return self._row_to_task(row)

    def all(self) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, title, priority, due, status FROM tasks ORDER BY id").fetchall()
        return [self._row_to_task(row) for row in rows]

    def update(self, task: Task) -> None:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET title = ?, priority = ?, due = ?, status = ? WHERE id = ?",
                (task.title, task.priority.value, _iso(task.due), task.status.value, task.id),
            )
            if cursor.rowcount == 0:
                raise TaskNotFoundError(task.id)

    def delete(self, task_id: int) -> Task:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, priority, due, status FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError(task_id)
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return self._row_to_task(row)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def open_repository(path: str | Path) -> TaskRepository:
    """Choose the back end from the file name: ``.json`` or ``.db``/``.sqlite``/``.sqlite3``."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return JsonTaskRepository(path)
    if suffix in SQLITE_SUFFIXES:
        return SqliteTaskRepository(path)
    raise StorageError(f"unsupported data file {path.name!r}: use a .json, .db or .sqlite file")
