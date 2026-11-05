"""Command-line interface: turns arguments into calls on the model and a repository.

This is the only module that reads ``sys.argv``-style arguments, prints, or decides
exit codes. It reads the clock once (``date.today()``) unless ``--today`` is given,
which is how the tests stay independent of the real date.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date

from .models import (
    Priority,
    Status,
    Task,
    TaskError,
    due_note,
    filter_tasks,
    parse_due,
    parse_iso_date,
    sort_tasks,
)
from .storage import StorageError, TaskNotFoundError, TaskRepository, open_repository

DEFAULT_DB = "tasks.json"
STATUS_FILTERS: dict[str, frozenset[Status] | None] = {
    "open": frozenset({Status.TODO, Status.IN_PROGRESS}),
    "todo": frozenset({Status.TODO}),
    "in-progress": frozenset({Status.IN_PROGRESS}),
    "done": frozenset({Status.DONE}),
    "all": None,
}
PRIORITY_CHOICES = [priority.label for priority in Priority]


def today_option(value: str) -> date:
    """argparse type for ``--today``: exactly ``YYYY-MM-DD`` (bad dates exit with code 2)."""
    try:
        return parse_iso_date(value)
    except TaskError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def build_parser() -> argparse.ArgumentParser:
    """Create the parser: global ``--db`` and ``--today``, then one subcommand."""
    parser = argparse.ArgumentParser(
        prog="task_manager",
        description="A to-do list with priorities, due dates and statuses.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"data file: .json, or .db/.sqlite for SQLite (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--today",
        type=today_option,
        help="treat this date (YYYY-MM-DD) as today, for planning ahead and for tests",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add = commands.add_parser("add", help="add a task")
    add.add_argument("title", help="what needs doing (quote it if it contains spaces)")
    add.add_argument("-p", "--priority", type=str.lower, choices=PRIORITY_CHOICES, default="medium")
    add.add_argument("--due", help="YYYY-MM-DD, today, tomorrow or +N (days from today)")

    show = commands.add_parser("list", help="list tasks, most urgent first")
    show.add_argument("--status", type=str.lower, choices=list(STATUS_FILTERS), default="open")
    show.add_argument("-p", "--priority", type=str.lower, choices=PRIORITY_CHOICES)
    show.add_argument("--overdue", action="store_true", help="only tasks whose due date has passed")

    for name, help_text in (
        ("start", "mark a task as in progress"),
        ("done", "mark a task as done"),
        ("delete", "delete a task"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("id", type=int, help="the task id shown by list")
    return parser


def format_task_table(tasks: list[Task], today: date) -> str:
    """Render tasks as an aligned table with a summary line."""
    if not tasks:
        return "No tasks found."
    lines = [f"{'ID':>4}  {'Priority':<8}  {'Status':<11}  {'Due':<10}  Title"]
    for task in tasks:
        due = task.due.isoformat() if task.due else "-"
        note = due_note(task, today)
        title = f"{task.title} ({note})" if note else task.title
        lines.append(f"{task.id:>4}  {task.priority.label:<8}  {task.status.value:<11}  {due:<10}  {title}")
    overdue = sum(task.is_overdue(today) for task in tasks)
    lines.append(f"{len(tasks)} task(s), {overdue} overdue.")
    return "\n".join(lines)


def _describe(task: Task) -> str:
    details = task.priority.label + (f", due {task.due.isoformat()}" if task.due else "")
    return f"{task.title} ({details})"


def run_add(repo: TaskRepository, args: argparse.Namespace, today: date) -> str:
    due = parse_due(args.due, today) if args.due is not None else None
    task = repo.add(args.title, priority=Priority.parse(args.priority), due=due)
    return f"Added task {task.id}: {_describe(task)}."


def run_list(repo: TaskRepository, args: argparse.Namespace, today: date) -> str:
    tasks = filter_tasks(
        repo.all(),
        statuses=STATUS_FILTERS[args.status],
        priority=Priority.parse(args.priority) if args.priority else None,
        overdue_on=today if args.overdue else None,
    )
    return format_task_table(sort_tasks(tasks), today)


def run_start(repo: TaskRepository, args: argparse.Namespace, today: date) -> str:
    task = repo.get(args.id)
    if task.status is Status.IN_PROGRESS:
        return f"Task {task.id} is already in progress."
    repo.update(task.start())
    return f"Started task {task.id}: {task.title}."


def run_done(repo: TaskRepository, args: argparse.Namespace, today: date) -> str:
    task = repo.get(args.id)
    if task.is_done:
        return f"Task {task.id} is already done."
    repo.update(task.complete())
    return f"Completed task {task.id}: {task.title}."


def run_delete(repo: TaskRepository, args: argparse.Namespace, today: date) -> str:
    task = repo.delete(args.id)
    return f"Deleted task {task.id}: {task.title}."


COMMANDS: dict[str, Callable[[TaskRepository, argparse.Namespace, date], str]] = {
    "add": run_add,
    "list": run_list,
    "start": run_start,
    "done": run_done,
    "delete": run_delete,
}


def main(argv: list[str] | None = None) -> int:
    """Run one command. Returns 0 on success, 1 for errors the user can fix.

    argparse itself exits with code 2 for usage errors such as an unknown command.
    """
    args = build_parser().parse_args(argv)
    today = args.today if args.today is not None else date.today()
    try:
        repo = open_repository(args.db)
        message = COMMANDS[args.command](repo, args, today)
    except (TaskError, TaskNotFoundError, StorageError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
