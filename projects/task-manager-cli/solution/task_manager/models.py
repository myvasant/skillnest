"""Domain model: tasks, priorities, statuses and the rules about them.

This module knows nothing about files, databases or the command line. Every rule
(validation, status changes, due dates, sorting, filtering) works on plain values,
so it can be tested without touching the disk, and "today" is always a parameter.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

MAX_TITLE_LENGTH = 200
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
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
        """The lower-case name used in files and on the command line."""
        return self.name.lower()

    @classmethod
    def parse(cls, text: str) -> Priority:
        """Parse ``"high"``, ``" Low "``... (case-insensitive) or raise TaskError."""
        try:
            return cls[text.strip().upper()]
        except (KeyError, AttributeError):
            raise TaskError(f"unknown priority {text!r}; use low, medium or high") from None


class Status(Enum):
    """Where a task is in its life cycle: TODO -> IN_PROGRESS -> DONE."""

    TODO = "todo"
    IN_PROGRESS = "in-progress"
    DONE = "done"

    @classmethod
    def parse(cls, text: str) -> Status:
        """Parse ``"todo"``, ``"in-progress"`` or ``"done"`` (case-insensitive) or raise TaskError."""
        try:
            return cls(text.strip().lower())
        except (ValueError, AttributeError):
            raise TaskError(f"unknown status {text!r}; use todo, in-progress or done") from None


def normalise_title(title: str) -> str:
    """Collapse runs of whitespace; reject empty or over-long titles."""
    if not isinstance(title, str):
        raise TaskError("title must be text")
    cleaned = " ".join(title.split())
    if not cleaned:
        raise TaskError("title cannot be empty")
    if len(cleaned) > MAX_TITLE_LENGTH:
        raise TaskError(f"title is too long ({len(cleaned)} characters; the maximum is {MAX_TITLE_LENGTH})")
    return cleaned


@dataclass(frozen=True)
class Task:
    """One task. Immutable: changes return a new Task (see ``start`` and ``complete``)."""

    id: int
    title: str
    priority: Priority = Priority.MEDIUM
    due: date | None = None
    status: Status = Status.TODO

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or not isinstance(self.id, int) or self.id < 1:
            raise TaskError(f"task id must be a positive whole number, not {self.id!r}")
        # A frozen dataclass cannot assign normally; this is the documented way to
        # store a cleaned-up value during initialisation.
        object.__setattr__(self, "title", normalise_title(self.title))
        if not isinstance(self.priority, Priority):
            raise TaskError(f"priority must be a Priority, not {self.priority!r}")
        if not isinstance(self.status, Status):
            raise TaskError(f"status must be a Status, not {self.status!r}")
        if self.due is not None and (isinstance(self.due, datetime) or not isinstance(self.due, date)):
            raise TaskError(f"due must be a date or None, not {self.due!r}")

    @property
    def is_done(self) -> bool:
        """True once the task is completed."""
        return self.status is Status.DONE

    def start(self) -> Task:
        """Return this task marked IN_PROGRESS (unchanged if it already is)."""
        if self.is_done:
            raise TaskError(f"task {self.id} is already done")
        return replace(self, status=Status.IN_PROGRESS)

    def complete(self) -> Task:
        """Return this task marked DONE (unchanged if it already is)."""
        return replace(self, status=Status.DONE)

    def is_overdue(self, today: date) -> bool:
        """True if the task has a due date before ``today`` and is not done."""
        return self.due is not None and self.due < today and not self.is_done

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready data: enums become their labels, dates ISO strings."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.label,
            "due": self.due.isoformat() if self.due else None,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Task:
        """Rebuild a Task from ``to_dict`` output, validating everything (raises TaskError)."""
        if not isinstance(data, Mapping):
            raise TaskError("a task must be an object with id, title, priority, due and status")
        missing = {"id", "title", "priority", "status"} - data.keys()
        if missing:
            raise TaskError(f"missing field(s): {', '.join(sorted(missing))}")
        due_text = data.get("due")
        due = None if due_text is None else parse_iso_date(due_text)
        return cls(
            id=data["id"],
            title=data["title"],
            priority=Priority.parse(data["priority"]),
            due=due,
            status=Status.parse(data["status"]),
        )


def parse_iso_date(text: Any) -> date:
    """Parse exactly ``YYYY-MM-DD`` into a date or raise TaskError."""
    if not isinstance(text, str) or not _ISO_DATE.fullmatch(text):
        raise TaskError(f"invalid date {text!r}; use YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise TaskError(f"{text} is not a real calendar date") from None


def parse_due(text: str, today: date) -> date:
    """Parse a due date typed by the user, relative to ``today``.

    Accepts ``YYYY-MM-DD``, ``today``, ``tomorrow`` or ``+N`` (N days from today).
    A new task cannot already be late, so dates before ``today`` raise TaskError.
    """
    value = text.strip().lower()
    relative = _RELATIVE_DAYS.fullmatch(value)
    if value == "today":
        due = today
    elif value == "tomorrow":
        due = today + timedelta(days=1)
    elif relative:
        due = today + timedelta(days=int(relative[1]))
    else:
        try:
            due = parse_iso_date(value)
        except TaskError as exc:
            raise TaskError(
                f"invalid due date {text!r}: use YYYY-MM-DD, today, tomorrow or +N ({exc})"
            ) from None
    if due < today:
        raise TaskError(f"due date {due.isoformat()} is in the past")
    return due


def due_note(task: Task, today: date) -> str:
    """A short human note about the due date: ``overdue by 2 days``, ``due tomorrow``..."""
    if task.due is None or task.is_done:
        return ""
    days = (task.due - today).days
    if days < 0:
        return f"overdue by {-days} day{'s' if days < -1 else ''}"
    if days == 0:
        return "due today"
    if days == 1:
        return "due tomorrow"
    return f"due in {days} days"


def sort_key(task: Task) -> tuple[bool, int, bool, date, int]:
    """Order: open tasks first, then priority (high first), then due date (none last), then id."""
    return (task.is_done, -task.priority.value, task.due is None, task.due or date.max, task.id)


def sort_tasks(tasks: Iterable[Task]) -> list[Task]:
    """Return the tasks in the order of :func:`sort_key` (a new list)."""
    return sorted(tasks, key=sort_key)


def filter_tasks(
    tasks: Iterable[Task],
    *,
    statuses: Collection[Status] | None = None,
    priority: Priority | None = None,
    overdue_on: date | None = None,
) -> list[Task]:
    """Keep the tasks that match every given criterion (None means "any")."""
    return [
        task
        for task in tasks
        if (statuses is None or task.status in statuses)
        and (priority is None or task.priority is priority)
        and (overdue_on is None or task.is_overdue(overdue_on))
    ]
