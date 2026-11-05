# Task manager CLI (starter kit)

A command-line to-do list with priorities, due dates and statuses, built as a small **package**
with three layers (`models`, `storage`, `cli`) and two interchangeable storage back ends: a JSON
file and an SQLite database. Standard library only.

## The problem

You want a to-do list that lives in your terminal and in a file you own. It must:

* add tasks with a priority (`low`, `medium`, `high`) and an optional due date (`2026-10-30`,
  `today`, `tomorrow` or `+3` for "in three days");
* list open tasks most-urgent-first (priority, then due date), mark overdue ones, and filter by
  status, priority or "overdue";
* move tasks through `todo` → `in-progress` → `done`, and delete them;
* keep the data in `tasks.json`, or in an SQLite database when the file ends in `.db`/`.sqlite`,
  with exactly the same behaviour;
* never corrupt or silently overwrite the data file, and never let input be interpreted as SQL.

The interesting part is the **structure**: the rules about tasks know nothing about files or the
command line, storage hides behind one interface, and only the CLI prints. That separation is
what lets you swap JSON for SQLite without touching the rest, and test each layer on its own.

## What's in this folder

| Path | Purpose |
|---|---|
| `starter/task_manager/` | Your package: `models.py`, `storage.py`, `cli.py` with docstrings, TODOs and `NotImplementedError`; `__init__.py` and `__main__.py` are complete. |
| `solution/task_manager/` | The reference solution. Try the milestones yourself first. |
| `tests/test_task_manager.py` | 122 behaviour tests, one class per milestone. The storage contract runs once per back end. |
| `conftest.py` | Makes the tests import `starter/` (default) or `solution/` (`GW_TARGET=solution`). |
| `requirements.txt` | Only `pytest`; the program itself needs nothing beyond Python 3.11+ (`sqlite3` is built in). |

## Setup

Run these commands from inside this folder (`projects/task-manager-cli`).

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
once, or skip activation and call `.\.venv\Scripts\python.exe` directly.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                    # all tests, against starter/ (they fail until you implement it)
python -m pytest -k Milestone1      # just one milestone
python -m pytest -k Milestone4 -x   # stop at the first failure
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest
Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

Every data file lives in pytest's `tmp_path`, and every test passes "today" explicitly (`--today`
on the command line), so the results never depend on the real date or on your own task list.

## Running the program

The package runs with `python -m task_manager` from the folder that contains it:

```text
> cd starter            (or: cd solution)
> python -m task_manager --today 2026-10-22 add "Submit report" -p high --due tomorrow
Added task 1: Submit report (high, due 2026-10-23).
> python -m task_manager --today 2026-10-22 add "Read a book" -p low
Added task 2: Read a book (low).
> python -m task_manager --today 2026-10-22 add "Fix bike" --due 2026-10-25
Added task 3: Fix bike (medium, due 2026-10-25).
> python -m task_manager --today 2026-10-22 list
  ID  Priority  Status       Due         Title
   1  high      todo         2026-10-23  Submit report (due tomorrow)
   3  medium    todo         2026-10-25  Fix bike (due in 3 days)
   2  low       todo         -           Read a book
3 task(s), 0 overdue.
> python -m task_manager start 3
Started task 3: Fix bike.
> python -m task_manager done 1
Completed task 1: Submit report.
> python -m task_manager --today 2026-10-27 list --status all
  ID  Priority  Status       Due         Title
   3  medium    in-progress  2026-10-25  Fix bike (overdue by 2 days)
   2  low       todo         -           Read a book
   1  high      done         2026-10-23  Submit report
3 task(s), 1 overdue.
> python -m task_manager add "Late" --due 2026-10-01
error: due date 2026-10-01 is in the past
> python -m task_manager delete 9
error: task 9 does not exist
> python -m task_manager --db tasks.db add "Stored in SQLite"
Added task 1: Stored in SQLite (medium).
```

Without `--today` the program uses the real date. `--db` chooses the data file (default
`tasks.json` in the current folder); `.db`, `.sqlite` and `.sqlite3` select SQLite.

### Output reference

| Command | Prints (exit code 0) |
|---|---|
| `add TITLE [-p P] [--due WHEN]` | `Added task <id>: <title> (<priority>[, due <date>]).` |
| `list [--status S] [-p P] [--overdue]` | a table (header `ID Priority Status Due Title`; `-` for no due date; the due note in brackets after the title), then `<n> task(s), <m> overdue.`, or `No tasks found.` |
| `start ID` | `Started task <id>: <title>.` or `Task <id> is already in progress.` |
| `done ID` | `Completed task <id>: <title>.` or `Task <id> is already done.` |
| `delete ID` | `Deleted task <id>: <title>.` |

`list --status` accepts `open` (default: todo and in-progress), `todo`, `in-progress`, `done` and
`all`. Problems the user can fix print `error: <message>` to stderr and exit with 1 (empty title,
past or invalid due date, unknown id, starting a done task, a corrupt data file, an unsupported
file suffix). argparse exits with 2 for usage errors (unknown command, missing title, bad priority,
an id that is not a number, a `--today` that is not `YYYY-MM-DD`).

## Milestones

1. **Model** (`-k Milestone1`, `models.py`): `Priority.parse`, `Status.parse`, `normalise_title`,
   `Task.__post_init__` validation (a frozen dataclass), `start`/`complete`/`is_done`,
   `to_dict`/`from_dict` and `parse_iso_date`.
2. **Rules** (`-k Milestone2`, `models.py`): `parse_due` (relative dates, nothing in the past),
   `Task.is_overdue`, `due_note`, `sort_key`/`sort_tasks` and `filter_tasks`, all with an explicit
   `today`.
3. **JSON storage** (`-k Milestone3`, `storage.py`): `atomic_write_text` and
   `JsonTaskRepository`: a versioned file with `next_id` so ids are never reused, strict
   validation on load, and atomic saves.
4. **SQLite storage** (`-k Milestone4`, `storage.py`): `SqliteTaskRepository` with a schema,
   `?` placeholders only, connections that are always closed, and `open_repository`. The same
   contract tests as milestone 3 must pass.
5. **CLI and structure** (`-k Milestone5`, `cli.py`): `today_option`, `build_parser`,
   `format_task_table` and `main`. The tests also check the layering: `models` imports neither
   storage nor CLI code, `storage` never imports the CLI, and only `cli.py` prints.

## Security notes

* **SQL injection.** Values always travel as `?` parameters (`conn.execute("... WHERE id = ?",
  (task_id,))`), never inside the SQL text. A test stores the title `Robert'); DROP TABLE tasks;--`
  and another scans `storage.py` to make sure no SQL is built with f-strings or `.format()`.
* **Untrusted data files.** A JSON file can be edited by hand or by another program, so every
  task is validated on load, and a corrupt file is reported instead of being overwritten.
* **Atomic writes.** Saving writes a temporary file in the same folder and swaps it in with
  `os.replace`, so a crash or full disk leaves the old file intact. `tempfile.mkstemp` creates the
  file readable only by you on macOS and Linux.
* **Where the data lives.** Task titles can be private. Keep `tasks.json`/`tasks.db` out of
  version control (add them to `.gitignore`) and out of shared folders.
