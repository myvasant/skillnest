"""Domain model: tasks, priorities, statuses and the rules about them.  (STARTER)

This module must know nothing about files, databases or the command line: do not
import json, sqlite3, argparse, .storage or .cli here (a test checks). Every rule
works on plain values and "today" is always a parameter, never date.today().

Milestone 1: Priority.parse, Status.parse, normalise_title, Task.__post_init__,
             Task.start / complete / is_done, to_dict, from_dict, parse_iso_date.
Milestone 2: parse_due, Task.is_overdue, due_note, sort_key, sort_tasks, filter_tasks.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

MAX_TITLE_LENGTH = 200
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")  # exactly YYYY-MM-DD
_RELATIVE_DAYS = re.compile(r"\+(\d{1,4})")  # "+3" means three days from today


class TaskError(ValueError):
    """Invalid task data or an impossible change, with a message for the user."""


class Priority(Enum):
    """How important a task is. The values order them: HIGH (3) > MEDIUM (2) > LOW (1)."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        """The lower-case name used in files and on the command line ("high")."""
        return self.name.lower()

    @classmethod
    def parse(cls, text: str) -> Priority:
        """Parse "high", " Low "... (case-insensitive, spaces ignored).

        Raise TaskError mentioning "priority" for anything else. Hint: ``cls["HIGH"]``.
        """
        # TODO (milestone 1)
        raise NotImplementedError("Priority.parse")


class Status(Enum):
    """Where a task is in its life cycle: TODO -> IN_PROGRESS -> DONE."""

    TODO = "todo"
    IN_PROGRESS = "in-progress"
    DONE = "done"

    @classmethod
    def parse(cls, text: str) -> Status:
        """Parse "todo", "in-progress" or "done" (case-insensitive); else TaskError ("status")."""
        # TODO (milestone 1): hint: cls("done") looks a member up by its value
        raise NotImplementedError("Status.parse")


def normalise_title(title: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends.

    Raise TaskError mentioning "empty" if nothing is left, and "too long" if the
    result is longer than MAX_TITLE_LENGTH characters.
    """
    # TODO (milestone 1)
    raise NotImplementedError("normalise_title")


@dataclass(frozen=True)
class Task:
    """One task. Immutable: changes return a new Task (see ``start`` and ``complete``)."""

    id: int
    title: str
    priority: Priority = Priority.MEDIUM
    due: date | None = None
    status: Status = Status.TODO

    def __post_init__(self) -> None:
        # TODO (milestone 1): validate every field and raise TaskError when invalid:
        #  * id: an int >= 1 (and not a bool: True is an int in Python!)
        #  * title: store the cleaned title with
        #        object.__setattr__(self, "title", normalise_title(self.title))
        #    (a frozen dataclass cannot assign self.title = ... directly)
        #  * priority / status: real Priority / Status members, not strings
        #  * due: None or a date (a datetime is a date subclass: reject it too)
        pass

    @property
    def is_done(self) -> bool:
        """True once the task is completed."""
        raise NotImplementedError("Task.is_done")

    def start(self) -> Task:
        """Return a copy marked IN_PROGRESS; TaskError "task N is already done" if DONE.

        Hint: dataclasses.replace(self, status=...) makes the modified copy.
        """
        raise NotImplementedError("Task.start")

    def complete(self) -> Task:
        """Return a copy marked DONE."""
        raise NotImplementedError("Task.complete")

    def is_overdue(self, today: date) -> bool:
        """True if the task has a due date before ``today`` and is not done. (milestone 2)"""
        raise NotImplementedError("Task.is_overdue")

    def to_dict(self) -> dict[str, Any]:
        """Return {"id", "title", "priority" (label), "due" (ISO text or None), "status" (value)}."""
        raise NotImplementedError("Task.to_dict")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Task:
        """Rebuild a Task from ``to_dict`` output, validating everything (raise TaskError).

        Reject non-mappings, missing id/title/priority/status, unknown labels and
        due dates that are not exactly YYYY-MM-DD real dates ("due" may be missing or None).
        """
        raise NotImplementedError("Task.from_dict")


def parse_iso_date(text: Any) -> date:
    """Parse exactly ``YYYY-MM-DD`` (use _ISO_DATE.fullmatch first) or raise TaskError.

    Note: date.fromisoformat alone also accepts "20261030" since Python 3.11.
    """
    # TODO (milestone 1)
    raise NotImplementedError("parse_iso_date")


def parse_due(text: str, today: date) -> date:
    """Parse a due date typed by the user, relative to ``today``.

    Accept YYYY-MM-DD, "today", "tomorrow" or "+N" (N days from today), ignoring case
    and surrounding spaces. Raise TaskError mentioning "invalid due date" for any
    other text, and "in the past" for dates before today.
    """
    # TODO (milestone 2)
    raise NotImplementedError("parse_due")


def due_note(task: Task, today: date) -> str:
    """ "overdue by 1 day", "overdue by 3 days", "due today", "due tomorrow",
    "due in 5 days", or "" for tasks that are done or have no due date."""
    # TODO (milestone 2)
    raise NotImplementedError("due_note")


def sort_key(task: Task) -> tuple[bool, int, bool, date, int]:
    """Open tasks first, then priority (high first), then due date (none last), then id.

    Hint: (task.is_done, -task.priority.value, task.due is None, task.due or date.max, task.id)
    """
    # TODO (milestone 2)
    raise NotImplementedError("sort_key")


def sort_tasks(tasks: Iterable[Task]) -> list[Task]:
    """Return a new list sorted with sort_key."""
    # TODO (milestone 2)
    raise NotImplementedError("sort_tasks")


def filter_tasks(
    tasks: Iterable[Task],
    *,
    statuses: Collection[Status] | None = None,
    priority: Priority | None = None,
    overdue_on: date | None = None,
) -> list[Task]:
    """Keep the tasks that match every given criterion (None means "any").

    ``overdue_on=today`` keeps only tasks that are overdue on that date.
    """
    # TODO (milestone 2)
    raise NotImplementedError("filter_tasks")
