# CSV processor (starter kit)

Clean a messy sales export and summarise it per region, product or month, streaming one row at a
time with the standard library's `csv` module. Standard library only.

## The problem

A shop exports its orders as CSV. The file is the kind you get in real life: stray spaces, `NA` and
empty cells, a quantity typed as `ten`, an impossible date, a duplicated order, a price written
`$11.50`, a row broken by an unquoted comma. You need to:

* parse every value into the right type (`int`, `Decimal`, `date`) and normalise text;
* treat the usual "no value" markers (`""`, `NA`, `n/a`, `NaN`, `null`, `None`, `-`) as missing;
* reject bad rows with the line number and a reason, instead of crashing or silently guessing;
* group the good rows and compute count, total, mean, min and max per group;
* print a readable report and optionally write the per-group table to a CSV that is safe to open
  in a spreadsheet;
* do it all in one streaming pass, so a 5 GB file works as well as a 5-line one.

Copy this into `sales.csv` to try the program (it is also the data the tests use):

```csv
order_id,order_date,region,product,quantity,unit_price
A001,2026-03-01,North,Notebook,3,4.50
A002,2026-03-01, south ,Pen,10,1.20
A003,2026-03-02,North,Stapler,1,12.00
A004,2026-03-05,,Notebook,2,4.50
A005,2026-03-07,South,Pen,ten,1.20
A006,2026-02-30,North,Pen,1,1.20
A007,2026-04-02,East,Notebook,NA,4.50
A003,2026-04-03,North,Stapler,1,12.00
A008,2026-04-04,east,Stapler,2,$11.50
A009,2026-04-05,West,Desk lamp,1,1,200.00
```

## What's in this folder

| Path | Purpose |
|---|---|
| `starter/csv_processor.py` | Your file: constants, exceptions and dataclass fields are given; every function raises `NotImplementedError`. |
| `solution/csv_processor.py` | The reference solution. Try the milestones yourself first. |
| `tests/test_csv_processor.py` | The behaviour tests, one class per milestone. |
| `conftest.py` | Makes the tests import `starter/` (default) or `solution/` (`GW_TARGET=solution`). |
| `requirements.txt` | Only `pytest`; the program itself needs nothing beyond Python 3.11+. |

## Setup

Run these commands from inside this folder (`projects/csv-processor`).

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
python -m pytest -k Milestone3 -x   # stop at the first failure
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest
Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

Most tests feed CSV text through `io.StringIO`; tests that need real files use pytest's `tmp_path`.

## Running the program

```text
> python starter/csv_processor.py sales.csv
Rows read: 10 | kept: 5 | rejected: 5
Rejected rows by column:
  order_date   1
  order_id     1
  quantity     2
  row          1
Examples:
  line 6: quantity: 'ten' is not a whole number
  line 7: order_date: '2026-02-30' is not a real calendar date
  line 8: quantity: value is missing
  line 9: order_id: duplicate of line 4
  line 11: row: 1 more field(s) than the header (an unquoted comma?)

Revenue by region
Region        Count       Total        Mean         Min         Max
East              1       23.00       23.00       23.00       23.00
North             2       25.50       12.75       12.00       13.50
South             1       12.00       12.00       12.00       12.00
Unknown           1        9.00        9.00        9.00        9.00
TOTAL             5       69.50       13.90        9.00       23.00

> python starter/csv_processor.py sales.csv --group-by month --value quantity --summary-csv summary.csv --max-examples 0
...
Quantity by month
Month         Count       Total        Mean         Min         Max
2026-03           4          16        4.00           1          10
2026-04           1           2        2.00           2           2
TOTAL             5          18        3.60           1          10

Summary written to summary.csv
> python starter/csv_processor.py missing.csv
error: missing.csv does not exist
```

Options: `--group-by region|product|month`, `--value revenue|quantity`, `--summary-csv PATH`,
`--max-examples N` (rejected rows to show; all of them are still counted). Exit code 0 = success,
1 = the file cannot be processed, 2 = bad usage.

## Milestones

1. **Values** (`-k Milestone1`): `is_missing`, `clean_text`, `parse_whole_number`, `parse_money`,
   `parse_iso_date`. Parsers raise `ValueError` with a message that quotes the bad value.
2. **Rows** (`-k Milestone2`): `clean_row` turns a raw `dict` into a typed `Sale` (with `revenue` and
   `month` properties) or raises `RowError(column, message)`.
3. **Streaming** (`-k Milestone3`): the generators `read_rows` (`csv.DictReader`, header checks,
   line numbers, surplus fields) and `clean_rows` (yields `Sale` or `Rejected`, catches duplicates).
4. **Aggregation** (`-k Milestone4`): `GroupStats` (running count/total/min/max, mean rounded half up),
   `aggregate`, `build_report` (one pass, bounded examples) and `summarise_file`.
5. **Report and CLI** (`-k Milestone5`): `format_report`, `escape_formula`, `write_summary_csv`,
   `build_parser` and `main`.

## Security notes

* **CSV / formula injection.** A cell such as `=HYPERLINK("http://evil.example","Click")` becomes a
  live formula when someone opens your output in Excel or LibreOffice. `escape_formula` prefixes
  text starting with `=`, `+`, `-`, `@`, tab or carriage return with `'` before it is written.
* **Untrusted input.** Every value is validated; nothing from the file is ever passed to `eval`, a
  shell or SQL. The `csv` module's field size limit (128 KiB by default) stops a single giant field
  from exhausting memory; the resulting `csv.Error` is reported, not ignored.
* **Bounded memory.** Rows are streamed and only the first `--max-examples` rejected rows are kept.
  The duplicate check stores one entry per order id, which is the only state that grows with the file.
* **Paths.** The tool reads and writes only the paths you give it. Do not run it on files from
  unknown sources inside folders where an overwritten `--summary-csv` would hurt.
