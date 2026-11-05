"""Exploratory data analysis of a seeded synthetic retail dataset (reference solution).

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
    rows = {}
    for col in numeric_columns(df):
        if col in exclude:
            continue
        s = df[col]
        rows[col] = {
            "count": int(s.count()),
            "missing": int(s.isna().sum()),
            "mean": s.mean(),
            "std": s.std(),
            "min": s.min(),
            "q1": s.quantile(0.25),
            "median": s.median(),
            "q3": s.quantile(0.75),
            "max": s.max(),
        }
    return pd.DataFrame.from_dict(rows, orient="index").astype({"count": "int64", "missing": "int64"})


def categorical_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summary of every text/categorical column.

    Returns:
        Index = column name; columns ``count`` (non-missing), ``unique`` (distinct non-missing values),
        ``top`` (most frequent value; ties broken alphabetically) and ``top_share`` (its fraction of the
        non-missing values).
    """
    rows = {}
    for col in categorical_columns(df):
        s = df[col].dropna().astype(str)
        counts = s.value_counts()
        if counts.empty:
            rows[col] = {"count": 0, "unique": 0, "top": None, "top_share": float("nan")}
            continue
        best = counts.max()
        top = sorted(counts[counts == best].index)[0]
        rows[col] = {"count": int(s.size), "unique": int(counts.size), "top": top, "top_share": best / s.size}
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------------------
# Milestone 2: missing values and outliers
# ---------------------------------------------------------------------------


def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    """Count and percentage of missing values per column.

    Returns:
        Index = column name; columns ``n_missing`` (int) and ``pct_missing`` (0-100). Sorted by
        ``n_missing`` descending, ties by column name, so the worst columns come first.
    """
    n_missing = df.isna().sum()
    report = pd.DataFrame(
        {"n_missing": n_missing.astype("int64"), "pct_missing": 100.0 * n_missing / max(len(df), 1)}
    )
    report.index.name = "column"
    ordered = report.reset_index().sort_values(["n_missing", "column"], ascending=[False, True])
    return ordered.set_index("column")


def missing_by_group(df: pd.DataFrame, column: str, by: str) -> pd.Series:
    """Fraction (0-1) of missing ``column`` values within each group of ``by``, sorted by group.

    If the rates differ a lot between groups the values are *not missing completely at random*, and
    dropping incomplete rows would bias any comparison between those groups.
    """
    for col in (column, by):
        if col not in df.columns:
            raise KeyError(f"column {col!r} not in DataFrame")
    rates = df[column].isna().groupby(df[by], observed=True).mean().sort_index()
    rates.name = f"{column}_missing_rate"
    return rates


def iqr_bounds(series: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """Tukey fences ``(Q1 - k*IQR, Q3 + k*IQR)`` using pandas' default (linear) quantiles."""
    if k < 0:
        raise ValueError(f"k must be non-negative, got {k}")
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - k * iqr), float(q3 + k * iqr)


def iqr_outliers(series: pd.Series, k: float = 1.5) -> pd.Series:
    """Boolean mask: True where a value lies strictly outside the Tukey fences. Missing values are False."""
    lower, upper = iqr_bounds(series, k)
    return ((series < lower) | (series > upper)).fillna(False).astype(bool)


def zscore_outliers(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    """Boolean mask: True where ``|x - mean| / std`` exceeds ``threshold`` (sample std). Missing → False.

    Note that extreme values inflate the mean and std they are measured against, so this method misses
    outliers in small samples that the IQR method catches.
    """
    std = series.std()
    if not std or math.isnan(std):
        return pd.Series(False, index=series.index)
    z = (series - series.mean()).abs() / std
    return (z > threshold).fillna(False).astype(bool)


def outlier_report(df: pd.DataFrame, columns: Sequence[str] | None = None, k: float = 1.5) -> pd.DataFrame:
    """IQR outlier summary for the given numeric columns (default: all numeric columns).

    Returns:
        Index = column; columns ``lower, upper, n_outliers, pct_outliers`` (percentage of non-missing
        values), sorted by ``n_outliers`` descending then column name.
    """
    cols = list(columns) if columns is not None else numeric_columns(df)
    rows = {}
    for col in cols:
        if col not in df.columns:
            raise KeyError(f"column {col!r} not in DataFrame")
        lower, upper = iqr_bounds(df[col], k)
        n_out = int(iqr_outliers(df[col], k).sum())
        rows[col] = {
            "lower": lower,
            "upper": upper,
            "n_outliers": n_out,
            "pct_outliers": 100.0 * n_out / max(int(df[col].count()), 1),
        }
    report = pd.DataFrame.from_dict(rows, orient="index")
    report.index.name = "column"
    ordered = report.reset_index().sort_values(["n_outliers", "column"], ascending=[False, True])
    return ordered.set_index("column")


# ---------------------------------------------------------------------------
# Milestone 3: group comparisons
# ---------------------------------------------------------------------------


def group_summary(df: pd.DataFrame, by: str, value: str) -> pd.DataFrame:
    """Aggregate ``value`` per group of ``by``.

    Returns:
        Index = group; columns ``count, mean, median, std, total, share`` where ``share`` is the group's
        fraction of the overall total. Sorted by ``mean`` descending.
    """
    for col in (by, value):
        if col not in df.columns:
            raise KeyError(f"column {col!r} not in DataFrame")
    grouped = df.groupby(by, observed=True)[value]
    summary = grouped.agg(count="count", mean="mean", median="median", std="std", total="sum")
    summary["share"] = summary["total"] / summary["total"].sum()
    return summary.sort_values("mean", ascending=False)


def compare_groups(df: pd.DataFrame, by: str, value: str, a: Any, b: Any) -> dict[str, float]:
    """Compare the mean of ``value`` between groups ``a`` and ``b`` of column ``by``.

    Returns:
        ``n_a, n_b, mean_a, mean_b, diff`` (mean_a - mean_b), ``welch_t`` (Welch's t statistic,
        unequal variances) and ``cohens_d`` (difference in pooled standard deviations). Missing values
        are ignored.

    Raises:
        ValueError: if either group has fewer than two non-missing values.
    """
    xa = df.loc[df[by] == a, value].dropna().to_numpy(dtype=float)
    xb = df.loc[df[by] == b, value].dropna().to_numpy(dtype=float)
    if xa.size < 2 or xb.size < 2:
        raise ValueError(f"each group needs at least 2 values (got {xa.size} for {a!r}, {xb.size} for {b!r})")
    va, vb = xa.var(ddof=1), xb.var(ddof=1)
    diff = xa.mean() - xb.mean()
    pooled = math.sqrt(((xa.size - 1) * va + (xb.size - 1) * vb) / (xa.size + xb.size - 2))
    se = math.sqrt(va / xa.size + vb / xb.size)
    return {
        "n_a": int(xa.size),
        "n_b": int(xb.size),
        "mean_a": float(xa.mean()),
        "mean_b": float(xb.mean()),
        "diff": float(diff),
        "welch_t": float(diff / se) if se else float("nan"),
        "cohens_d": float(diff / pooled) if pooled else float("nan"),
    }


# ---------------------------------------------------------------------------
# Milestone 4: correlation
# ---------------------------------------------------------------------------


def correlation_matrix(
    df: pd.DataFrame, method: str = "pearson", exclude: Sequence[str] = ()
) -> pd.DataFrame:
    """Pairwise correlation of the numeric columns (``method``: pearson, spearman or kendall)."""
    if method not in {"pearson", "spearman", "kendall"}:
        raise ValueError(f"unknown correlation method {method!r}")
    cols = [c for c in numeric_columns(df) if c not in exclude]
    return df[cols].corr(method=method)


def top_correlations(
    df: pd.DataFrame, n: int = 5, method: str = "pearson", exclude: Sequence[str] = ()
) -> pd.DataFrame:
    """The ``n`` strongest correlations between distinct numeric columns.

    Each unordered pair appears once (``var_a`` comes before ``var_b`` in column order).

    Returns:
        Columns ``var_a, var_b, r``, sorted by ``|r|`` descending (ties by name), index 0..n-1.
    """
    corr = correlation_matrix(df, method, exclude)
    cols = list(corr.columns)
    pairs = [
        {"var_a": cols[i], "var_b": cols[j], "r": float(corr.iloc[i, j])}
        for i in range(len(cols))
        for j in range(i + 1, len(cols))
        if not math.isnan(corr.iloc[i, j])
    ]
    pairs.sort(key=lambda p: (-abs(p["r"]), p["var_a"], p["var_b"]))
    return pd.DataFrame(pairs[:n], columns=["var_a", "var_b", "r"])


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
    missing = missing_report(df)
    outliers = outlier_report(df, ["revenue", "units"])
    by_region = group_summary(df, "region", "revenue")
    return {
        "n_rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "missing": {c: float(p) for c, p in missing["pct_missing"].items() if p > 0},
        "satisfaction_missing_by_channel": {
            str(k): float(v) for k, v in missing_by_group(df, "satisfaction", "channel").items()
        },
        "outliers": {c: int(n) for c, n in outliers["n_outliers"].items()},
        "revenue": {
            "mean": float(df["revenue"].mean()),
            "median": float(df["revenue"].median()),
            "max": float(df["revenue"].max()),
        },
        "revenue_by_region": by_region,
        "top_region": str(by_region.index[0]),
        "channel_satisfaction": compare_groups(df, "channel", "satisfaction", "online", "store"),
        "correlations": top_correlations(df, n=5, exclude=["order_id"]),
    }


def _findings_bullets(f: dict[str, Any]) -> list[str]:
    """Turn the numbers into plain-English findings."""
    region = f["revenue_by_region"]
    top = f["top_region"]
    sat = f["channel_satisfaction"]
    strongest = f["correlations"].iloc[0]
    rev = f["revenue"]
    rates = f["satisfaction_missing_by_channel"]
    bullets = [
        f"**{top}** has the highest mean revenue per order ({region.loc[top, 'mean']:.2f}) "
        f"and {region.loc[top, 'share']:.1%} of total revenue.",
        f"Online orders score lower on satisfaction than store orders ({sat['mean_a']:.2f} vs "
        f"{sat['mean_b']:.2f}; Welch t = {sat['welch_t']:.1f}, Cohen's d = {sat['cohens_d']:.2f}).",
        f"The strongest relationship is between `{strongest['var_a']}` and `{strongest['var_b']}` "
        f"(r = {strongest['r']:.2f}). Correlation is not causation: check the mechanism before acting.",
        f"`revenue` has {f['outliers']['revenue']} values outside the 1.5 x IQR fences. Revenue is "
        f"right-skewed (mean {rev['mean']:.2f} vs median {rev['median']:.2f}), so most flagged orders are "
        f"large but plausible; investigate the most extreme ones (max {rev['max']:.2f}) instead of "
        "dropping every flagged row, and report medians alongside means.",
    ]
    if "satisfaction" in f["missing"]:
        rate_text = ", ".join(f"{k} {v:.0%}" for k, v in rates.items())
        bullets.append(
            f"`satisfaction` is missing in {f['missing']['satisfaction']:.1f}% of rows ({rate_text}). "
            "The rate depends on the channel, so it is not missing completely at random: dropping "
            "incomplete rows would bias the channel comparison."
        )
    return bullets


def render_report(findings: dict[str, Any]) -> str:
    """Render the findings as a Markdown report with a written ``## Findings`` section."""
    missing_lines = [f"- `{c}`: {p:.1f}% missing" for c, p in findings["missing"].items()] or ["- none"]
    outlier_lines = [f"- `{c}`: {n} outliers (1.5 x IQR rule)" for c, n in findings["outliers"].items()]
    corr = findings["correlations"].set_index(["var_a", "var_b"])
    corr.index = [f"{a} ~ {b}" for a, b in corr.index]
    corr.index.name = "pair"
    parts = [
        "# Retail orders: exploratory data analysis",
        "",
        "## Dataset",
        f"{findings['n_rows']} orders, {findings['n_columns']} columns (synthetic, seeded).",
        "",
        "## Data quality",
        *missing_lines,
        *outlier_lines,
        "",
        "## Revenue by region",
        to_markdown_table(findings["revenue_by_region"]),
        "",
        "## Strongest correlations",
        to_markdown_table(corr),
        "",
        "## Findings",
        *[f"{i}. {b}" for i, b in enumerate(_findings_bullets(findings), start=1)],
        "",
        "## Limitations",
        "- The data is synthetic: these findings describe the generator, not real customers.",
        "- Group differences are descriptive; no causal claim is made.",
        "",
    ]
    return "\n".join(parts)


def write_report(df: pd.DataFrame, path: Path | str) -> Path:
    """Analyse ``df`` and write the Markdown report to ``path`` (parent folders are created)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(build_findings(df)), encoding="utf-8")
    return out


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
