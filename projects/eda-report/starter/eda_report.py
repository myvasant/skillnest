"""Exploratory data analysis of a seeded synthetic retail dataset (starter).

Every analysis step is a small function that takes a DataFrame and returns a DataFrame or a dict, so
the numbers that end up in the written report can be checked by tests. Nothing here draws plots: a
report built from tested numbers is more trustworthy than a chart nobody re-checks.

Run the whole analysis from the command line::

    python solution/eda_report.py --out report.md
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REGIONS: tuple[str, ...] = ("North", "South", "East", "West")
CATEGORIES: tuple[str, ...] = ("Electronics", "Grocery", "Clothing", "Home")
CHANNELS: tuple[str, ...] = ("online", "store")
BASE_PRICES: tuple[float, ...] = (220.0, 12.0, 45.0, 80.0)  # same order as CATEGORIES


# ---------------------------------------------------------------------------
# Provided: the dataset (identical in starter/ and solution/)
# ---------------------------------------------------------------------------


def make_retail_data(n_rows: int = 1000, seed: int = 42) -> pd.DataFrame:
    """Generate a reproducible synthetic table of retail orders.

    The data is *designed* to contain things an analyst should find: missing customer ages and
    satisfaction scores, a handful of bulk orders that are extreme outliers, a region that sells more
    units per order, and online orders whose satisfaction falls as delivery takes longer.

    Args:
        n_rows: Number of orders to generate (at least 20).
        seed: Seed for NumPy's random generator; the same seed always gives the same table.

    Returns:
        One row per order with columns ``order_id, order_date, region, category, channel, units,
        unit_price, discount, revenue, delivery_days, customer_age, satisfaction``.
    """
    if n_rows < 20:
        raise ValueError(f"n_rows must be at least 20, got {n_rows}")
    rng = np.random.default_rng(seed)
    region = rng.choice(REGIONS, size=n_rows, p=[0.3, 0.25, 0.25, 0.2])
    category = rng.choice(CATEGORIES, size=n_rows, p=[0.2, 0.35, 0.25, 0.2])
    channel = rng.choice(CHANNELS, size=n_rows, p=[0.55, 0.45])
    online = channel == "online"

    base_price = dict(zip(CATEGORIES, BASE_PRICES, strict=True))
    unit_price = np.array([base_price[c] for c in category]) * rng.lognormal(0.0, 0.25, n_rows)
    units = rng.poisson(np.where(region == "West", 4.5, 2.5)) + 1
    bulk = rng.choice(n_rows, size=max(2, n_rows // 200), replace=False)
    units[bulk] *= 25  # a few bulk orders: genuine but extreme
    discount = np.where(online, np.round(rng.uniform(0.0, 0.3, n_rows), 2), 0.0)
    revenue = np.round(units * unit_price * (1 - discount), 2)
    delivery_days = np.where(online, rng.integers(1, 11, n_rows), 0)
    satisfaction = np.clip(np.round(4.7 - 0.3 * delivery_days + rng.normal(0, 0.5, n_rows)), 1, 5)
    age = np.clip(np.round(rng.normal(41, 13, n_rows)), 18, 90)

    df = pd.DataFrame(
        {
            "order_id": np.arange(1, n_rows + 1),
            "order_date": pd.Timestamp("2025-01-01")
            + pd.to_timedelta(rng.integers(0, 365, n_rows), unit="D"),
            "region": region,
            "category": category,
            "channel": channel,
            "units": units.astype("int64"),
            "unit_price": np.round(unit_price, 2),
            "discount": discount,
            "revenue": revenue,
            "delivery_days": delivery_days.astype("int64"),
            "customer_age": age,
            "satisfaction": satisfaction,
        }
    )
    df.loc[rng.random(n_rows) < 0.06, "customer_age"] = np.nan
    df.loc[rng.random(n_rows) < np.where(online, 0.15, 0.05), "satisfaction"] = np.nan
    return df


def to_markdown_table(df: pd.DataFrame, float_format: str = "{:.2f}") -> str:
    """Render a DataFrame (including its index) as a GitHub-flavoured Markdown table."""
    index_name = df.index.name or ""
    header = [str(index_name), *map(str, df.columns)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for idx, *values in df.itertuples(name=None):
        cells = [str(idx)]
        for value in values:
            if isinstance(value, float | np.floating):
                cells.append("" if math.isnan(value) else float_format.format(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Milestone 1: summary statistics
# ---------------------------------------------------------------------------


def numeric_columns(df: pd.DataFrame) -> list[str]:
    """Names of the numeric (int/float, not bool) columns, in table order."""
    return [
        c
        for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])
    ]


def categorical_columns(df: pd.DataFrame) -> list[str]:
    """Names of the text or categorical columns, in table order."""
    return [
        c
        for c in df.columns
        if isinstance(df[c].dtype, pd.CategoricalDtype)
        or pd.api.types.is_object_dtype(df[c])
        or pd.api.types.is_string_dtype(df[c])
    ]


def numeric_summary(df: pd.DataFrame, exclude: Sequence[str] = ()) -> pd.DataFrame:
    """Summary statistics for every numeric column.

    Returns:
        One row per numeric column (index = column name) with columns
        ``count, missing, mean, std, min, q1, median, q3, max``. ``count`` counts non-missing values
        and ``std`` is the sample standard deviation (ddof=1), as in ``Series.std``.
    """
    # TODO: loop over numeric_columns(df), skipping names in `exclude`.
    # TODO: for each column build a dict: count (non-missing, s.count()), missing (s.isna().sum()),
    #   mean, std (sample, ddof=1), min, q1 (s.quantile(0.25)), median, q3, max.
    # TODO: return pd.DataFrame.from_dict(rows, orient="index") with int count/missing columns.
    raise NotImplementedError("TODO: implement numeric_summary()")


def categorical_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summary of every text/categorical column.

    Returns:
        Index = column name; columns ``count`` (non-missing), ``unique`` (distinct non-missing values),
        ``top`` (most frequent value; ties broken alphabetically) and ``top_share`` (its fraction of the
        non-missing values).
    """
    # TODO: loop over categorical_columns(df); drop missing values first.
    # TODO: use value_counts(); `top` is the most frequent value (break ties alphabetically),
    #   `top_share` is its count divided by the number of non-missing values.
    raise NotImplementedError("TODO: implement categorical_summary()")


# ---------------------------------------------------------------------------
# Milestone 2: missing values and outliers
# ---------------------------------------------------------------------------


def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    """Count and percentage of missing values per column.

    Returns:
        Index = column name; columns ``n_missing`` (int) and ``pct_missing`` (0-100). Sorted by
        ``n_missing`` descending, ties by column name, so the worst columns come first.
    """
    # TODO: df.isna().sum() counts missing values per column.
    # TODO: pct_missing = 100 * n_missing / len(df).
    # TODO: sort by n_missing descending, then by column name (hint: reset_index, sort_values, set_index).
    raise NotImplementedError("TODO: implement missing_report()")


def missing_by_group(df: pd.DataFrame, column: str, by: str) -> pd.Series:
    """Fraction (0-1) of missing ``column`` values within each group of ``by``, sorted by group.

    If the rates differ a lot between groups the values are *not missing completely at random*, and
    dropping incomplete rows would bias any comparison between those groups.
    """
    # TODO: check both columns exist (raise KeyError with a clear message).
    # TODO: df[column].isna() is a boolean Series; group it by df[by] and take the mean.
    raise NotImplementedError("TODO: implement missing_by_group()")


def iqr_bounds(series: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """Tukey fences ``(Q1 - k*IQR, Q3 + k*IQR)`` using pandas' default (linear) quantiles."""
    # TODO: raise ValueError if k is negative.
    # TODO: q1 = series.quantile(0.25), q3 = series.quantile(0.75), iqr = q3 - q1.
    # TODO: return (q1 - k * iqr, q3 + k * iqr) as floats.
    raise NotImplementedError("TODO: implement iqr_bounds()")


def iqr_outliers(series: pd.Series, k: float = 1.5) -> pd.Series:
    """Boolean mask: True where a value lies strictly outside the Tukey fences. Missing values are False."""
    # TODO: use iqr_bounds(); a value is an outlier if it is strictly below lower or above upper.
    # TODO: comparisons with NaN are False, but make sure the result is a plain bool Series.
    raise NotImplementedError("TODO: implement iqr_outliers()")


def zscore_outliers(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    """Boolean mask: True where ``|x - mean| / std`` exceeds ``threshold`` (sample std). Missing → False.

    Note that extreme values inflate the mean and std they are measured against, so this method misses
    outliers in small samples that the IQR method catches.
    """
    # TODO: z = |x - mean| / std (sample std). Guard against std == 0 or NaN (return all False).
    # TODO: return z > threshold as a bool Series, with missing values False.
    raise NotImplementedError("TODO: implement zscore_outliers()")


def outlier_report(df: pd.DataFrame, columns: Sequence[str] | None = None, k: float = 1.5) -> pd.DataFrame:
    """IQR outlier summary for the given numeric columns (default: all numeric columns).

    Returns:
        Index = column; columns ``lower, upper, n_outliers, pct_outliers`` (percentage of non-missing
        values), sorted by ``n_outliers`` descending then column name.
    """
    # TODO: default columns: numeric_columns(df); raise KeyError for unknown columns.
    # TODO: for each column: lower, upper (iqr_bounds), n_outliers (iqr_outliers(...).sum()),
    #   pct_outliers = 100 * n_outliers / number of non-missing values.
    # TODO: sort by n_outliers descending, then column name.
    raise NotImplementedError("TODO: implement outlier_report()")


# ---------------------------------------------------------------------------
# Milestone 3: group comparisons
# ---------------------------------------------------------------------------


def group_summary(df: pd.DataFrame, by: str, value: str) -> pd.DataFrame:
    """Aggregate ``value`` per group of ``by``.

    Returns:
        Index = group; columns ``count, mean, median, std, total, share`` where ``share`` is the group's
        fraction of the overall total. Sorted by ``mean`` descending.
    """
    # TODO: raise KeyError if `by` or `value` is not a column.
    # TODO: df.groupby(by, observed=True)[value].agg(count="count", mean="mean", ...) builds named columns.
    # TODO: share = total / total.sum(); sort by mean, highest first.
    raise NotImplementedError("TODO: implement group_summary()")


def compare_groups(df: pd.DataFrame, by: str, value: str, a: Any, b: Any) -> dict[str, float]:
    """Compare the mean of ``value`` between groups ``a`` and ``b`` of column ``by``.

    Returns:
        ``n_a, n_b, mean_a, mean_b, diff`` (mean_a - mean_b), ``welch_t`` (Welch's t statistic,
        unequal variances) and ``cohens_d`` (difference in pooled standard deviations). Missing values
        are ignored.

    Raises:
        ValueError: if either group has fewer than two non-missing values.
    """
    # TODO: select the non-missing values of `value` for group a and group b as float arrays.
    # TODO: raise ValueError if either group has fewer than 2 values.
    # TODO: welch_t = diff / sqrt(var_a / n_a + var_b / n_b) with sample variances (ddof=1).
    # TODO: cohens_d = diff / pooled_sd, pooled_sd = sqrt(((n_a-1)var_a + (n_b-1)var_b) / (n_a + n_b - 2)).
    raise NotImplementedError("TODO: implement compare_groups()")


# ---------------------------------------------------------------------------
# Milestone 4: correlation
# ---------------------------------------------------------------------------


def correlation_matrix(
    df: pd.DataFrame, method: str = "pearson", exclude: Sequence[str] = ()
) -> pd.DataFrame:
    """Pairwise correlation of the numeric columns (``method``: pearson, spearman or kendall)."""
    # TODO: raise ValueError unless method is pearson, spearman or kendall.
    # TODO: select numeric_columns(df) minus `exclude`, then use DataFrame.corr(method=...).
    raise NotImplementedError("TODO: implement correlation_matrix()")


def top_correlations(
    df: pd.DataFrame, n: int = 5, method: str = "pearson", exclude: Sequence[str] = ()
) -> pd.DataFrame:
    """The ``n`` strongest correlations between distinct numeric columns.

    Each unordered pair appears once (``var_a`` comes before ``var_b`` in column order).

    Returns:
        Columns ``var_a, var_b, r``, sorted by ``|r|`` descending (ties by name), index 0..n-1.
    """
    # TODO: take each unordered pair once: i < j over the matrix columns (skip the diagonal).
    # TODO: skip NaN correlations (constant columns).
    # TODO: sort by -|r|, then var_a, var_b; keep the first n; columns var_a, var_b, r.
    raise NotImplementedError("TODO: implement top_correlations()")


# ---------------------------------------------------------------------------
# Milestone 5: findings and the written report
# ---------------------------------------------------------------------------


def build_findings(df: pd.DataFrame) -> dict[str, Any]:
    """Run the analysis on the retail table and collect the headline numbers.

    Returns:
        A dict with keys ``n_rows``, ``n_columns``, ``missing`` ({column: pct} for columns with any
        missing values), ``satisfaction_missing_by_channel`` ({channel: rate 0-1}), ``outliers``
        ({column: count} for revenue and units), ``revenue`` ({mean, median, max}),
        ``revenue_by_region`` (the :func:`group_summary` DataFrame), ``top_region``,
        ``channel_satisfaction`` (the :func:`compare_groups` dict for online vs store) and
        ``correlations`` (the :func:`top_correlations` DataFrame, excluding ``order_id``).
    """
    # TODO: call your milestone 1-4 functions and collect the numbers listed in the docstring.
    # TODO: keep DataFrames as DataFrames (revenue_by_region, correlations) and numbers as plain floats/ints.
    raise NotImplementedError("TODO: implement build_findings()")


def render_report(findings: dict[str, Any]) -> str:
    """Render the findings as a Markdown report with a written ``## Findings`` section."""
    # TODO: build the Markdown as a list of lines and join with "\n".
    # TODO: sections: '# ...' title, '## Dataset', '## Data quality', '## Revenue by region' (use
    #   to_markdown_table), '## Strongest correlations', '## Findings', '## Limitations'.
    # TODO: the Findings section is prose: numbered sentences that state each result with its numbers,
    #   e.g. which region earns most, how online and store satisfaction differ, and what the
    #   missing-value pattern means. Write them from the findings dict, never hard-code numbers.
    raise NotImplementedError("TODO: implement render_report()")


def write_report(df: pd.DataFrame, path: Path | str) -> Path:
    """Analyse ``df`` and write the Markdown report to ``path`` (parent folders are created)."""
    # TODO: create the parent folder, write render_report(build_findings(df)) as UTF-8, return the Path.
    raise NotImplementedError("TODO: implement write_report()")


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point: generate the data and write the report."""
    parser = argparse.ArgumentParser(description="EDA report for the synthetic retail dataset.")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("report.md"))
    args = parser.parse_args(argv)
    path = write_report(make_retail_data(args.rows, args.seed), args.out)
    print(f"Report written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
