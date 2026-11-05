# Expense tracker (starter kit)

A command-line expense tracker that stores its data in a JSON file: add expenses, list and filter
them, and summarise spending by category or by month. Standard library only.

## The problem

You want to know where your money goes without handing your bank data to an app. The tool must:

* record an expense with an amount, a category, a date and an optional note;
* refuse bad input with a clear message (`-5`, `abc`, `1.234`, `2026-02-30`, an empty category);
* store everything in one JSON file, written **atomically** so a crash can never leave it half-written;
* report a corrupt data file clearly instead of crashing or silently overwriting it;
* list expenses (optionally for one category and/or month) and total them per category or per month.

Money is stored as `decimal.Decimal`, never `float`: `0.1 + 0.2` is `0.30000000000000004` in binary
floating point, so float totals drift by fractions of a cent. In the JSON file amounts are strings
(`"12.50"`) so no precision is lost on the way to disk and back.

## What's in this folder

| Path | Purpose |
|---|---|
| `starter/expense_tracker.py` | Your file: every function has a docstring and TODOs and raises `NotImplementedError`. |
| `solution/expense_tracker.py` | The reference solution. Try the milestones yourself first. |
| `tests/test_expense_tracker.py` | The behaviour tests, one class per milestone. |
| `conftest.py` | Makes the tests import `starter/` (default) or `solution/` (`GW_TARGET=solution`). |
| `requirements.txt` | Only `pytest`; the program itself needs nothing beyond Python 3.11+. |

## Setup

Run these commands from inside this folder (`projects/expense-tracker`).

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
python -m pytest -k Milestone2 -x   # stop at the first failure
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest
Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

The tests use pytest's `tmp_path` for every file and pass dates explicitly (`main(..., today=...)`),
so they never touch your real data and never depend on today's date.

## Running the program

```text
> python starter/expense_tracker.py add 12.50 Groceries --date 2026-10-01 -d "weekly shop"
Added 12.50 to groceries on 2026-10-01 (1 in total).
> python starter/expense_tracker.py add 3.20 transport --date 2026-10-02 -d bus
Added 3.20 to transport on 2026-10-02 (2 in total).
> python starter/expense_tracker.py add 30 groceries --date 2026-09-28 -d "big shop"
Added 30.00 to groceries on 2026-09-28 (3 in total).
> python starter/expense_tracker.py list
Date        Category             Amount  Description
2026-09-28  groceries             30.00  big shop
2026-10-01  groceries             12.50  weekly shop
2026-10-02  transport              3.20  bus
3 expense(s), total 45.70
> python starter/expense_tracker.py summary --by month
Month         Total
2026-09       30.00
2026-10       15.70
TOTAL         45.70
> python starter/expense_tracker.py add -5 food
error: amount must be greater than zero, not '-5'
> python starter/expense_tracker.py --file work.json list
No expenses found.
```

Without `--file` the data goes to `expenses.json` in the current folder. Without `--date`, `add`
uses today's date. The exit code is 0 on success, 1 for an error you can fix, 2 for bad usage.

## Milestones

1. **Model and validation** (`-k Milestone1`): `parse_amount`, `parse_date`, `parse_month`,
   `normalise_category`, `clean_description`, `make_expense`, and `Expense.month` / `to_dict` /
   `from_dict`.
2. **Safe JSON storage** (`-k Milestone2`): `load_expenses` (missing file = no expenses; corrupt or
   wrongly shaped files raise `ExpenseError` naming the file), `save_expenses` (temporary file in the
   same folder + `os.replace`, temporary file removed on failure) and `add_expense`.
3. **Filters and summaries** (`-k Milestone3`): `filter_expenses`, `total`, `summarise_by_category`,
   `summarise_by_month`, `format_expenses`, `format_summary`.
4. **Command-line interface** (`-k Milestone4`): `build_parser` with `add` / `list` / `summary`
   subcommands and a global `--file`, and `main`, which prints `error: ...` to stderr and returns 1
   for `ExpenseError` and `OSError`.

## Security notes

* The data file holds personal financial information: keep it out of version control (add
  `expenses.json` to `.gitignore`) and out of shared folders. `tempfile.mkstemp` creates the
  temporary file readable only by you on macOS/Linux, and `os.replace` keeps those permissions.
* Treat the JSON file as untrusted input: it is re-validated on load (`Expense.from_dict` calls
  `make_expense`), so a hand-edited or tampered file cannot inject negative or absurd amounts.
* Use `json`, never `pickle` or `eval`, for data files: loading a pickle can execute code.
* Inputs are bounded (amount limit, category and description lengths) and whitespace, including
  newlines, is collapsed, so a note cannot break the table output.
