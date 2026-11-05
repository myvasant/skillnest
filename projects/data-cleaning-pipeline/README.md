# Data-cleaning pipeline

Turn a messy customer export into a clean, validated table with a pipeline of small pure functions,
a step-by-step log and a validation report. Running the pipeline twice must give the same result
(idempotency), so a retried job can never corrupt data.

```text
raw export ─► normalise_columns ─► clean_text ─► lowercase(email) ─► standardise_categories(country)
           ─► parse_numbers / parse_dates ─► nullify_out_of_range(age) ─► deduplicate(email)
           ─► impute ─► validate(schema) ─► PipelineResult(data, log, report)
```

## The data

* `raw_customers()` — 10 hand-made rows with padded headers, mixed date formats (`2024-01-15`,
  `15/02/2024`, `March 3, 2024`), currency strings (`$300`, `1,200.50`, `1 050`), placeholders
  (`n/a`, `N/A`, blanks), an age of 200, a negative spend, an invalid date (`2024-13-01`) and two
  people who registered twice with differently-cased emails.
* `make_messy_customers(n_rows, seed)` — a larger seeded table with ~10% duplicate registrations, used
  to check that the pipeline scales and stays idempotent.

**Licence and limitations.** Both tables are generated in code by this project; the names are of
well-known computer scientists, and every email address uses the reserved `example.com` domain, so
there is no real personal data. Real exports have many more failure modes (encodings, Excel date
serials, merged cells); this project covers the most common ones.

## Setup

Windows (PowerShell):

```powershell
cd projects/data-cleaning-pipeline
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/data-cleaning-pipeline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                     # your code in starter/
python -m pytest -k Milestone3       # one milestone
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # Windows PowerShell
```

```bash
GW_TARGET=solution python -m pytest                                      # macOS / Linux
```

See the result: `python starter/cleaning_pipeline.py` prints the cleaned table and the report.

## Milestones

Work in `starter/cleaning_pipeline.py`. Every function returns a new DataFrame and never modifies its
input.

1. **Normalise** — `normalise_column_name`, `normalise_columns` (refuses collisions), `clean_text`
   (strip, placeholders become missing), `lowercase`, `standardise_categories` (idempotent mapping).
2. **Parse types** — `parse_dates` (formats tried in order; failures become `NaT`), `parse_numbers`
   (currency and separators; nullable `Int64` ids), `nullify_out_of_range`.
3. **Deduplicate** — `duplicate_mask` (case/space-insensitive keys; missing keys never match) and
   `deduplicate`.
4. **Impute** — `fit_imputer` (median, mean, mode, constant) separate from `apply_imputer`, and
   `impute`.
5. **Validate** — `check_column` and `validate` turn a schema of `ColumnRule`s into a
   `ValidationReport` that lists every failing check and row (it never raises on bad data).
6. **Pipeline and idempotency** — `run_pipeline` logs every step; `customer_steps` composes the steps
   with `functools.partial`; `clean_customers(clean_customers(raw).data)` changes nothing.
