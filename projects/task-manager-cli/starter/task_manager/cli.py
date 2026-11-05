"""Command-line interface (milestone 5).  (STARTER)

The only module that parses arguments, prints, or decides exit codes. It may read
the clock once (``date.today()``) when ``--today`` is not given.

Commands (see the README for the exact output):
    task_manager [--db FILE] [--today YYYY-MM-DD] add TITLE [-p low|medium|high] [--due WHEN]
    task_manager ... list [--status open|todo|in-progress|done|all] [-p PRIORITY] [--overdue]
    task_manager ... start ID | done ID | delete ID
"""

from __future__ import annotations

import argparse
from datetime import date

from .models import Status, Task

DEFAULT_DB = "tasks.json"
STATUS_FILTERS: dict[str, frozenset[Status] | None] = {
    "open": frozenset({Status.TODO, Status.IN_PROGRESS}),
    "todo": frozenset({Status.TODO}),
    "in-progress": frozenset({Status.IN_PROGRESS}),
    "done": frozenset({Status.DONE}),
    "all": None,
}


def today_option(value: str) -> date:
    """argparse type for --today: exactly YYYY-MM-DD, else argparse.ArgumentTypeError."""
    # TODO (milestone 5): reuse models.parse_iso_date
    raise NotImplementedError("today_option")


def build_parser() -> argparse.ArgumentParser:
    """Global --db (default tasks.json) and --today, then the subcommands add, list,
    start, done and delete (ids are type=int; priorities and statuses use choices)."""
    # TODO (milestone 5)
    raise NotImplementedError("build_parser")


def format_task_table(tasks: list[Task], today: date) -> str:
    """Header "ID  Priority  Status  Due  Title", one row per task (due "-" if none,
    the due_note in brackets after the title), then "N task(s), M overdue.".
    Return "No tasks found." for an empty list."""
    # TODO (milestone 5)
    raise NotImplementedError("format_task_table")


def main(argv: list[str] | None = None) -> int:
    """Run one command: print its message and return 0, or print "error: ..." to
    stderr and return 1 for TaskError, TaskNotFoundError and StorageError.
    argparse exits with code 2 for usage errors by itself."""
    # TODO (milestone 5)
    raise NotImplementedError("main")
