# EDA report: retail orders

Explore a seeded synthetic table of 1,000 retail orders and turn the analysis into a written report.
Every step is a function that returns a DataFrame or a dict, so the tests can check the numbers that
end up in your findings.

```text
make_retail_data() -> numeric/categorical summaries -> missing values & outliers
                   -> group comparisons -> correlations -> build_findings() -> report.md
```

## The dataset

`make_retail_data(n_rows=1000, seed=42)` (already implemented) generates one row per order:
`order_id, order_date, region, category, channel, units, unit_price, discount, revenue,
delivery_days, customer_age, satisfaction`.

It deliberately contains things a good analysis should find: missing ages and satisfaction scores
(missing more often for online orders), a few bulk orders, a region that buys more units per order,
and online satisfaction that falls as delivery takes longer.

**Licence and limitations.** The data is generated in code by this project (no download, no personal
data); you may use it freely. Because it is synthetic, the "findings" describe the generator's
assumptions, not real customer behaviour. Exact values can differ slightly between NumPy versions, so
the tests check patterns (for example "West has the highest mean revenue"), not exact generated values.

## Setup

Windows (PowerShell):

```powershell
cd projects/eda-report
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux:

```bash
cd projects/eda-report
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                      # tests your code in starter/
python -m pytest -k Milestone2        # just one milestone
```

To compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest; Remove-Item Env:GW_TARGET   # Windows PowerShell
```

```bash
GW_TARGET=solution python -m pytest                                      # macOS / Linux
```

Generate the report once everything passes:

```bash
python starter/eda_report.py --out report.md
```

## Milestones

Work in `starter/eda_report.py`. Each function has a docstring and `# TODO` notes.

1. **Summary statistics** — `numeric_summary` (count, missing, mean, std, quartiles) and
   `categorical_summary` (unique values, most frequent value and its share).
2. **Missing values and outliers** — `missing_report`, `missing_by_group` (is the data missing at
   random?), `iqr_bounds`, `iqr_outliers`, `zscore_outliers` and `outlier_report`.
3. **Group comparisons** — `group_summary` (per-group count/mean/median/std/total/share) and
   `compare_groups` (difference in means, Welch's t statistic, Cohen's d).
4. **Correlation** — `correlation_matrix` and `top_correlations` (each pair once, ranked by |r|).
5. **Findings report** — `build_findings` collects the headline numbers; `render_report` writes Markdown
   with a prose `## Findings` section generated from those numbers; `write_report` saves it.

## Optional: plots

Plots are not required and are not tested. If you want them, install matplotlib in *your* virtual
environment (`python -m pip install matplotlib`) and save figures to files (for example a histogram of
`log(revenue)`), linking them from the report.
