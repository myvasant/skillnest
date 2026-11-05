"""Persistence: one repository interface, two interchangeable back ends.  (STARTER)

* JsonTaskRepository (milestone 3): one versioned JSON file, saved atomically.
* SqliteTaskRepository (milestone 4): sqlite3 with ``?`` placeholders only.

Both raise TaskNotFoundError for unknown ids and StorageError for unreadable or
invalid data, and both must pass the same contract tests (RepositoryContract in
tests/test_task_manager.py). This module may import .models, never .cli or argparse.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from .models import Priority, Task

FORMAT_VERSION = 1
SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})

# The table for milestone 4. CHECK constraints are a second line of defence:
# the database itself refuses values that the model would never produce.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT    NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    priority INTEGER NOT NULL CHECK (priority IN (1, 2, 3)),
    due      TEXT,
    status   TEXT    NOT NULL CHECK (status IN ('todo', 'in-progress', 'done'))
)
"""


class StorageError(Exception):
    """The data file cannot be read or written, or its content is invalid."""


class TaskNotFoundError(LookupError):
    """No task has the requested id. str(error) is "task 7 does not exist"."""

    def __init__(self, task_id: int) -> None:
        super().__init__(f"task {task_id} does not exist")
        self.task_id = task_id


class TaskRepository(ABC):
    """Where tasks live. Every implementation must behave exactly the same."""

    @abstractmethod
    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        """Store a new TODO task under a new id (ids are never reused) and return it.

        Validate first (by building the Task): invalid input must not change any data.
        """

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


def atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically (milestone 3).

    tempfile.mkstemp(dir=path.parent) -> write (UTF-8), flush, os.fsync ->
    os.replace(temp, path). If anything fails, delete the temporary file and re-raise.
    """
    # TODO (milestone 3)
    raise NotImplementedError("atomic_write_text")


class JsonTaskRepository(TaskRepository):
    """Tasks in a JSON document: {"version": 1, "next_id": 4, "tasks": [...]} (milestone 3).

    * A missing file means no tasks (and reading must not create it).
    * Invalid JSON, a wrong shape or version, an invalid task, duplicate ids or a
      next_id that is not greater than every id: StorageError naming the file.
    * next_id is stored so that ids of deleted tasks are never reused.
    * Write errors (OSError) become StorageError("cannot write ...").
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        # TODO (milestone 3)
        raise NotImplementedError("JsonTaskRepository.add")

    def get(self, task_id: int) -> Task:
        # TODO (milestone 3)
        raise NotImplementedError("JsonTaskRepository.get")

    def all(self) -> list[Task]:
        # TODO (milestone 3)
        raise NotImplementedError("JsonTaskRepository.all")

    def update(self, task: Task) -> None:
        # TODO (milestone 3)
        raise NotImplementedError("JsonTaskRepository.update")

    def delete(self, task_id: int) -> Task:
        # TODO (milestone 3)
        raise NotImplementedError("JsonTaskRepository.delete")


class SqliteTaskRepository(TaskRepository):
    """Tasks in an SQLite database file, created on first use (milestone 4).

    * Run _SCHEMA in __init__ (CREATE TABLE IF NOT EXISTS).
    * Open a connection per operation and always close it (contextlib.closing, or a
      @contextmanager that also turns sqlite3.DatabaseError into StorageError).
    * Store priority as its number and due as ISO text; rebuild Task objects on read.
    * Only ever pass SQL as a constant string with ? placeholders (a test checks).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        # TODO (milestone 4): create the table

    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a transaction; always close it (make this a context manager)."""
        raise NotImplementedError("SqliteTaskRepository._connect")

    def add(self, title: str, *, priority: Priority = Priority.MEDIUM, due: date | None = None) -> Task:
        # TODO (milestone 4): INSERT ... VALUES (?, ?, ?, ?), then cursor.lastrowid is the id
        raise NotImplementedError("SqliteTaskRepository.add")

    def get(self, task_id: int) -> Task:
        # TODO (milestone 4)
        raise NotImplementedError("SqliteTaskRepository.get")

    def all(self) -> list[Task]:
        # TODO (milestone 4)
        raise NotImplementedError("SqliteTaskRepository.all")

    def update(self, task: Task) -> None:
        # TODO (milestone 4): cursor.rowcount == 0 means the id does not exist
        raise NotImplementedError("SqliteTaskRepository.update")

    def delete(self, task_id: int) -> Task:
        # TODO (milestone 4)
        raise NotImplementedError("SqliteTaskRepository.delete")


def open_repository(path: str | Path) -> TaskRepository:
    """Choose the back end from the file name: .json, or .db/.sqlite/.sqlite3 (any case).

    Raise StorageError mentioning "unsupported" for any other suffix. (milestone 4)
    """
    # TODO (milestone 4)
    raise NotImplementedError("open_repository")
