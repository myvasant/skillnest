"""A data-cleaning pipeline built from small pure functions (reference solution).

Each step takes a DataFrame and returns a *new* DataFrame; none mutates its input. Steps are composed
by :func:`run_pipeline`, which logs what every step did and validates the result against a schema.
The whole pipeline is idempotent: cleaning already-clean data changes nothing.

Run it on the provided messy table::

    python solution/cleaning_pipeline.py
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal

import numpy as np
import pandas as pd

Step = Callable[[pd.DataFrame], pd.DataFrame]
Kind = Literal["integer", "number", "string", "datetime", "boolean"]
Strategy = str | tuple[str, Any]

NULL_TOKENS: frozenset[str] = frozenset({"", "n/a", "na", "null", "none", "-", "?"})
DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y")
COUNTRY_CODES: tuple[tuple[str, str], ...] = (
    ("uk", "GB"), ("u.k.", "GB"), ("united kingdom", "GB"), ("great britain", "GB"),
    ("us", "US"), ("usa", "US"), ("u.s.", "US"), ("united states", "US"),
    ("nl", "NL"), ("netherlands", "NL"), ("the netherlands", "NL"),
    ("in", "IN"), ("india", "IN"),
)  # fmt: skip


# ---------------------------------------------------------------------------
# Provided: the messy input data (identical in starter/ and solution/)
# ---------------------------------------------------------------------------

RAW_COLUMNS: tuple[str, ...] = (
    " Customer ID",
    "Full Name",
    "Email ",
    "Signup Date",
    "Country",
    "Age",
    "Total Spend ($)",
)


def raw_customers() -> pd.DataFrame:
    """A small, hand-made export with the problems real exports have.

    Everything is text (as if read with ``pd.read_csv(..., dtype=str)``): padded headers and values,
    mixed date formats, currency strings, ``"n/a"`` placeholders, an impossible age, a negative
    spend, an invalid date and two customers who registered twice with differently-cased emails.
    """
    rows = [
        ("001", " Ada Lovelace ", "ADA@Example.com ", "2024-01-15", "uk", "36", "1,200.50"),
        ("002", "Grace Hopper", "grace@example.com", "15/02/2024", "USA", "", "$300"),
        ("003", "Alan Turing", "alan@example.com", "March 3, 2024", "U.K.", "41", "450"),
        ("001", "Ada Lovelace", "ada@example.com", "2024-01-15", "United Kingdom", "36", "1200.5"),
        ("004", "Katherine Johnson", "katherine@example.com", "2024-13-01", "us", "n/a", "75.25"),
        ("005", "Edsger Dijkstra", "", "2024-04-01", "Netherlands", "200", "-5"),
        ("006", "Radia Perlman", "  ", "01/05/2024", "usa", "52", "980"),
        ("007", "Tim Berners-Lee", "tim@example.com", "2024-05-20", "", "47", "N/A"),
        ("008", "Margaret Hamilton", "margaret@example.com", "June 9, 2024", "US", "33", "1 050"),
        ("009", "Grace H.", "GRACE@example.com", "2024-02-16", "US", "38", "310"),
    ]
    return pd.DataFrame(rows, columns=list(RAW_COLUMNS), dtype=object)


def make_messy_customers(n_rows: int = 300, seed: int = 0) -> pd.DataFrame:
    """Generate a larger messy export (seeded), with about 10% duplicate registrations.

    Args:
        n_rows: Number of distinct customers before duplicates are added.
        seed: Seed for NumPy's random generator; the same seed always gives the same table.
    """
    rng = np.random.default_rng(seed)
    countries = ("uk", "UK", "United Kingdom", "us", "USA", "United States", "NL", "Netherlands", "India", "")
    rows = []
    for i in range(1, n_rows + 1):
        day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=int(rng.integers(0, 365)))
        fmt = DATE_FORMATS[int(rng.integers(0, len(DATE_FORMATS)))]
        email = f"user{i}@example.com"
        if rng.random() < 0.3:
            email = f"  {email.upper()} "
        age = str(int(rng.integers(18, 90))) if rng.random() > 0.08 else str(rng.choice(["", "n/a", "NULL"]))
        spend = float(np.round(rng.gamma(2.0, 150.0), 2))
        spend_text = f"${spend:,.2f}" if rng.random() < 0.4 else f"{spend:.2f}"
        rows.append(
            (
                f"{i:04d}",
                f" Customer {i} ",
                email,
                day.strftime(fmt),
                str(rng.choice(countries)),
                age,
                spend_text,
            )
        )
    duplicates = rng.choice(len(rows), size=max(1, n_rows // 10), replace=False)
    for j in duplicates:
        cid, name, email, date, country, age, spend = rows[int(j)]
        rows.append((cid, name.strip(), email.strip().swapcase(), date, country, age, spend))
    return pd.DataFrame(rows, columns=list(RAW_COLUMNS), dtype=object)


def text_columns(df: pd.DataFrame) -> list[str]:
    """Columns holding text (object or string dtype), in table order."""
    return [
        c for c in df.columns if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])
    ]


def require_column(df: pd.DataFrame, column: str) -> None:
    """Raise a KeyError that lists the available columns if ``column`` is missing."""
    if column not in df.columns:
        raise KeyError(f"column {column!r} not found; available: {list(df.columns)}")


# ---------------------------------------------------------------------------
# Milestone 1: normalise column names and text
# ---------------------------------------------------------------------------


def normalise_column_name(name: str) -> str:
    """Turn a header into a snake_case identifier.

    Lower-case, replace every run of characters other than letters and digits with one underscore,
    and strip leading/trailing underscores: ``" Total Spend ($)" -> "total_spend"``.

    Raises:
        ValueError: if nothing usable is left (for example ``"$$"``).
    """
    cleaned = re.sub(r"[^0-9a-z]+", "_", str(name).strip().lower()).strip("_")
    if not cleaned:
        raise ValueError(f"column name {name!r} has no letters or digits")
    return cleaned


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every column name normalised.

    Raises:
        ValueError: if two columns would end up with the same name (for example ``"Age"`` and
            ``" age "``) — silently overwriting one would lose data.
    """
    names = [normalise_column_name(c) for c in df.columns]
    seen: dict[str, str] = {}
    for original, new in zip(df.columns, names, strict=True):
        if new in seen:
            raise ValueError(f"columns {seen[new]!r} and {original!r} both normalise to {new!r}")
        seen[new] = original
    out = df.copy()
    out.columns = names
    return out


def clean_text(df: pd.DataFrame, null_tokens: Iterable[str] = NULL_TOKENS) -> pd.DataFrame:
    """Strip whitespace in text columns and turn placeholder tokens into real missing values.

    ``"  n/a "``, ``""`` and ``"NULL"`` (case-insensitive, see ``NULL_TOKENS``) become missing;
    non-string cells are left untouched.
    """
    tokens = {t.casefold() for t in null_tokens}
    out = df.copy()
    for col in text_columns(out):
        stripped = out[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        is_null = stripped.map(lambda v: isinstance(v, str) and v.casefold() in tokens).astype(bool)
        out[col] = stripped.mask(is_null)
    return out


def lowercase(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Lower-case the string values of ``columns`` (for case-insensitive fields such as email)."""
    out = df.copy()
    for col in columns:
        require_column(out, col)
        out[col] = out[col].map(lambda v: v.lower() if isinstance(v, str) else v)
    return out


def standardise_categories(df: pd.DataFrame, column: str, mapping: Mapping[str, str]) -> pd.DataFrame:
    """Map spelling variants to one canonical value, case-insensitively.

    ``{"uk": "GB", "united kingdom": "GB"}`` turns ``"U.K."``-style variants listed in the mapping
    into ``"GB"``. Canonical values map to themselves and unknown values are left unchanged, so the
    step is idempotent. Missing values stay missing.
    """
    require_column(df, column)
    lookup = {v.casefold(): v for v in mapping.values()} | {k.casefold(): v for k, v in mapping.items()}
    out = df.copy()
    out[column] = out[column].map(lambda v: lookup.get(v.casefold(), v) if isinstance(v, str) else v)
    return out


# ---------------------------------------------------------------------------
# Milestone 2: parse dates and numbers
# ---------------------------------------------------------------------------


def parse_dates(df: pd.DataFrame, column: str, formats: Sequence[str] = DATE_FORMATS) -> pd.DataFrame:
    """Parse a text column into datetimes, trying each format in order.

    The first format that parses a value wins, so the order resolves ambiguous dates such as
    ``05/01/2024``. Values no format can parse become ``NaT`` (to be reported, not guessed). A column
    that is already datetime is returned unchanged.

    Raises:
        ValueError: if ``formats`` is empty.
    """
    require_column(df, column)
    if not formats:
        raise ValueError("give at least one date format")
    out = df.copy()
    if pd.api.types.is_datetime64_any_dtype(out[column]):
        return out
    text = out[column].map(lambda v: v.strip() if isinstance(v, str) else v)
    result: pd.Series | None = None
    for fmt in formats:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        result = parsed if result is None else result.where(result.notna(), parsed)
    out[column] = result
    return out


def parse_numbers(df: pd.DataFrame, column: str, integer: bool = False) -> pd.DataFrame:
    """Parse text such as ``"$1,200.50"`` or ``"1 050"`` into numbers.

    Currency symbols, thousands separators (commas, spaces) are removed; anything still not a number
    becomes missing. With ``integer=True`` the result is pandas' nullable ``Int64`` and values with a
    fractional part become missing. Numeric columns pass through (idempotent).
    """
    require_column(df, column)
    out = df.copy()
    s = out[column]
    if integer and pd.api.types.is_integer_dtype(s):
        out[column] = s.astype("Int64")
        return out
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        values = s.astype(float)
    else:
        text = s.map(lambda v: re.sub(r"[\s,$£€]", "", v) if isinstance(v, str) else v)
        values = pd.to_numeric(text, errors="coerce").astype(float)
    if integer:
        values = values.where(values % 1 == 0).astype("Int64")
    out[column] = values
    return out


def nullify_out_of_range(
    df: pd.DataFrame, column: str, min_value: float | None = None, max_value: float | None = None
) -> pd.DataFrame:
    """Replace values outside ``[min_value, max_value]`` with missing (an age of 200 is not data)."""
    require_column(df, column)
    out = df.copy()
    s = out[column]
    bad = pd.Series(False, index=s.index)
    if min_value is not None:
        bad |= (s < min_value).fillna(False).astype(bool)
    if max_value is not None:
        bad |= (s > max_value).fillna(False).astype(bool)
    out[column] = s.mask(bad)
    return out


# ---------------------------------------------------------------------------
# Milestone 3: deduplicate
# ---------------------------------------------------------------------------


def duplicate_mask(
    df: pd.DataFrame, keys: Sequence[str], keep: Literal["first", "last"] = "first"
) -> pd.Series:
    """True for rows that repeat an earlier (``keep="first"``) or later row's keys.

    Keys are compared after stripping and case-folding strings. Rows with a *missing* key are never
    duplicates: two customers without an email are not the same customer.
    """
    if not keys:
        raise ValueError("give at least one key column")
    for key in keys:
        require_column(df, key)
    normalised = pd.DataFrame(
        {k: df[k].map(lambda v: v.strip().casefold() if isinstance(v, str) else v) for k in keys}
    )
    missing_key = normalised.isna().any(axis=1)
    return normalised.duplicated(keep=keep) & ~missing_key


def deduplicate(
    df: pd.DataFrame, keys: Sequence[str], keep: Literal["first", "last"] = "first"
) -> pd.DataFrame:
    """Drop duplicate rows (see :func:`duplicate_mask`) and renumber the index from 0."""
    return df.loc[~duplicate_mask(df, keys, keep)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Milestone 4: impute
# ---------------------------------------------------------------------------


def fit_imputer(df: pd.DataFrame, strategies: Mapping[str, Strategy]) -> dict[str, Any]:
    """Learn one fill value per column.

    Strategies: ``"median"`` and ``"mean"`` (numeric columns), ``"mode"`` (most frequent value; the
    smallest if tied) or ``("constant", value)``. Fitting is separate from applying so that, in ML,
    fill values can be learned on training data only.

    Raises:
        KeyError: unknown column. ValueError: unknown strategy, a numeric strategy on a non-numeric
            column, or a column with no values to learn from.
    """
    fills: dict[str, Any] = {}
    for col, strategy in strategies.items():
        require_column(df, col)
        s = df[col]
        if isinstance(strategy, tuple):
            if len(strategy) != 2 or strategy[0] != "constant":
                raise ValueError(f"{col}: tuple strategies must be ('constant', value), got {strategy!r}")
            fills[col] = strategy[1]
            continue
        if strategy in ("median", "mean"):
            if not pd.api.types.is_numeric_dtype(s):
                raise ValueError(f"{col}: {strategy} needs a numeric column, got {s.dtype}")
            fill = s.median() if strategy == "median" else s.mean()
        elif strategy == "mode":
            modes = s.mode(dropna=True)
            fill = modes.iloc[0] if not modes.empty else np.nan
        else:
            raise ValueError(
                f"{col}: unknown strategy {strategy!r} (use median, mean, mode or ('constant', v))"
            )
        if pd.isna(fill):
            raise ValueError(f"{col}: no non-missing values to compute the {strategy}")
        fills[col] = fill
    return fills


def apply_imputer(df: pd.DataFrame, fills: Mapping[str, Any]) -> pd.DataFrame:
    """Fill missing values with the values learned by :func:`fit_imputer`."""
    out = df.copy()
    for col, fill in fills.items():
        require_column(out, col)
        out[col] = out[col].fillna(fill)
    return out


def impute(df: pd.DataFrame, strategies: Mapping[str, Strategy]) -> pd.DataFrame:
    """Fit and apply an imputer on the same table (fine for cleaning; not across train/test)."""
    return apply_imputer(df, fit_imputer(df, strategies))


# ---------------------------------------------------------------------------
# Milestone 5: validate against a schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnRule:
    """Expectations for one column."""

    kind: Kind
    nullable: bool = True
    unique: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed: frozenset[str] | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class Issue:
    """One failed check: which column, which check, how many rows and which row labels."""

    column: str
    check: str
    n_failed: int
    rows: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    """The result of :func:`validate`. ``ok`` is True when there are no issues."""

    n_rows: int
    issues: tuple[Issue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """True when every check passed."""
        return not self.issues

    def failed(self) -> set[tuple[str, str]]:
        """The set of ``(column, check)`` pairs that failed."""
        return {(i.column, i.check) for i in self.issues}

    def to_frame(self) -> pd.DataFrame:
        """One row per issue with columns ``column, check, n_failed, rows``."""
        return pd.DataFrame(
            [
                {"column": i.column, "check": i.check, "n_failed": i.n_failed, "rows": list(i.rows)}
                for i in self.issues
            ],
            columns=["column", "check", "n_failed", "rows"],
        )

    def to_markdown(self) -> str:
        """A short human-readable report."""
        if self.ok:
            return f"Validation passed: {self.n_rows} rows, no issues."
        lines = [f"Validation found {len(self.issues)} issue(s) in {self.n_rows} rows:", ""]
        lines += [
            f"- `{i.column}` failed **{i.check}** in {i.n_failed} row(s): {list(i.rows)}" for i in self.issues
        ]
        return "\n".join(lines)


_KIND_CHECKS: tuple[tuple[str, Callable[[pd.Series], bool]], ...] = (
    ("integer", pd.api.types.is_integer_dtype),
    ("number", lambda s: pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)),
    ("string", lambda s: pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)),
    ("datetime", pd.api.types.is_datetime64_any_dtype),
    ("boolean", pd.api.types.is_bool_dtype),
)


def _has_kind(s: pd.Series, kind: Kind) -> bool:
    for name, check in _KIND_CHECKS:
        if name == kind:
            return bool(check(s))
    raise ValueError(f"unknown kind {kind!r}")


def _issue(column: str, check: str, mask: pd.Series) -> Issue | None:
    mask = mask.fillna(False).astype(bool)
    if not mask.any():
        return None
    return Issue(column, check, int(mask.sum()), tuple(mask[mask].index.tolist()))


def check_column(s: pd.Series, rule: ColumnRule) -> list[Issue]:
    """Run every check in ``rule`` against one column; value checks ignore missing values."""
    col = str(s.name)
    if not _has_kind(s, rule.kind):
        return [Issue(col, "kind", int(s.size), ())]
    present = s.notna()
    candidates: list[tuple[str, pd.Series | None]] = [
        ("nullable", ~present if not rule.nullable else None),
        ("unique", s.duplicated(keep=False) & present if rule.unique else None),
        ("min", present & (s < rule.min_value) if rule.min_value is not None else None),
        ("max", present & (s > rule.max_value) if rule.max_value is not None else None),
        ("allowed", present & ~s.isin(rule.allowed) if rule.allowed is not None else None),
        (
            "pattern",
            present & ~s.map(lambda v: isinstance(v, str) and re.fullmatch(rule.pattern, v) is not None)
            if rule.pattern is not None
            else None,
        ),
    ]
    return [issue for name, mask in candidates if mask is not None and (issue := _issue(col, name, mask))]


def validate(
    df: pd.DataFrame, schema: Mapping[str, ColumnRule], allow_extra: bool = False
) -> ValidationReport:
    """Check ``df`` against ``schema`` and collect every problem (it never raises on bad data).

    Checks: ``missing_column``, ``unexpected_column`` (unless ``allow_extra``), ``kind``,
    ``nullable``, ``unique``, ``min``, ``max``, ``allowed`` and ``pattern``.
    """
    issues: list[Issue] = []
    for col, rule in schema.items():
        if col not in df.columns:
            issues.append(Issue(col, "missing_column", len(df)))
        else:
            issues.extend(check_column(df[col], rule))
    if not allow_extra:
        issues.extend(Issue(str(c), "unexpected_column", len(df)) for c in df.columns if c not in schema)
    return ValidationReport(n_rows=len(df), issues=tuple(issues))


# ---------------------------------------------------------------------------
# Milestone 6: the pipeline, its log and idempotency
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepLog:
    """What one step did: rows and missing cells before and after."""

    step: str
    rows_in: int
    rows_out: int
    missing_in: int
    missing_out: int


@dataclass(frozen=True)
class PipelineResult:
    """Cleaned data, a log of every step and the validation report."""

    data: pd.DataFrame
    log: tuple[StepLog, ...]
    report: ValidationReport

    def to_markdown(self) -> str:
        """The step log and the validation report as Markdown."""
        lines = [
            "## Cleaning log",
            "",
            "| step | rows in | rows out | missing in | missing out |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {s.step} | {s.rows_in} | {s.rows_out} | {s.missing_in} | {s.missing_out} |" for s in self.log
        ]
        return "\n".join([*lines, "", "## Validation", "", self.report.to_markdown(), ""])


def run_pipeline(
    df: pd.DataFrame, steps: Sequence[tuple[str, Step]], schema: Mapping[str, ColumnRule]
) -> PipelineResult:
    """Apply ``steps`` in order, logging each, then validate the result against ``schema``."""
    log: list[StepLog] = []
    current = df
    for name, step in steps:
        before_rows, before_missing = len(current), int(current.isna().sum().sum())
        current = step(current)
        log.append(StepLog(name, before_rows, len(current), before_missing, int(current.isna().sum().sum())))
    return PipelineResult(data=current, log=tuple(log), report=validate(current, schema))


def customer_steps() -> list[tuple[str, Step]]:
    """The cleaning steps for the customer export, in order."""
    return [
        ("normalise_columns", normalise_columns),
        ("clean_text", clean_text),
        ("lowercase_email", partial(lowercase, columns=["email"])),
        (
            "standardise_country",
            partial(standardise_categories, column="country", mapping=dict(COUNTRY_CODES)),
        ),
        ("parse_customer_id", partial(parse_numbers, column="customer_id", integer=True)),
        ("parse_signup_date", partial(parse_dates, column="signup_date", formats=DATE_FORMATS)),
        ("parse_age", partial(parse_numbers, column="age")),
        ("parse_total_spend", partial(parse_numbers, column="total_spend")),
        ("nullify_bad_ages", partial(nullify_out_of_range, column="age", min_value=18, max_value=120)),
        ("deduplicate_email", partial(deduplicate, keys=["email"])),
        ("impute", partial(impute, strategies={"age": "median", "country": ("constant", "unknown")})),
    ]


def customer_schema() -> dict[str, ColumnRule]:
    """What a clean customer table must look like."""
    return {
        "customer_id": ColumnRule("integer", nullable=False, unique=True),
        "full_name": ColumnRule("string", nullable=False),
        "email": ColumnRule("string", unique=True, pattern=r"[^@\s]+@[^@\s]+\.[a-z]{2,}"),
        "signup_date": ColumnRule("datetime", nullable=False),
        "country": ColumnRule(
            "string", nullable=False, allowed=frozenset({"GB", "US", "NL", "IN", "unknown"})
        ),
        "age": ColumnRule("number", nullable=False, min_value=18, max_value=120),
        "total_spend": ColumnRule("number", min_value=0),
    }


def clean_customers(df: pd.DataFrame) -> PipelineResult:
    """Run the customer pipeline. Running it again on its own output changes nothing."""
    return run_pipeline(df, customer_steps(), customer_schema())


def main() -> int:
    """Clean the provided raw table and print the cleaned data and report."""
    result = clean_customers(raw_customers())
    print(result.data.to_string())
    print()
    print(result.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
