"""Evaluate a saved model beyond one accuracy number (reference solution).

Given a saved classifier and labelled data with a group column, produce: slice metrics and fairness
gaps per group, confusion matrices, calibration (reliability table, Brier score, ECE), a decision
threshold chosen by expected cost, and a Markdown report.

The scenario: a synthetic loan-default model. ``default = 1`` means the applicant defaulted, and a
positive *prediction* flags an applicant as high risk — the adverse decision.

Run the whole thing::

    python solution/model_evaluation.py --out-dir evaluation
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import math
import pickle  # noqa: S403 - only used with the SHA-256 integrity check below
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES: tuple[str, ...] = ("income", "debt_ratio", "years_employed", "prior_defaults")
LABEL = "default"
GROUP = "group"


# ---------------------------------------------------------------------------
# Provided: data, model and helpers (identical in starter/ and solution/)
# ---------------------------------------------------------------------------


def make_applicants(n_rows: int = 6000, seed: int = 0) -> pd.DataFrame:
    """Generate a seeded synthetic loan dataset with two groups, ``A`` (70%) and ``B`` (30%).

    Group B has lower incomes on average *and* an extra default risk that none of the features
    capture (an omitted variable). A model that never sees the group still treats the groups
    differently through the features, and it under-predicts risk for B. The data is invented; the
    groups stand for any protected attribute.
    """
    rng = np.random.default_rng(seed)
    group = np.where(rng.random(n_rows) < 0.7, "A", "B")
    is_b = group == "B"
    income = np.round(rng.lognormal(np.where(is_b, 3.6, 3.9), 0.35), 1)  # thousands per year
    debt_ratio = np.round(rng.beta(2.0, 5.0, n_rows), 3)
    years = rng.integers(0, 30, n_rows)
    prior = rng.poisson(np.where(is_b, 0.35, 0.25))
    logit = (
        -1.3
        - 2.4 * (np.log(income) - 3.8)
        + 6.0 * (debt_ratio - 0.28)
        - 0.06 * (years - 15)
        + 1.0 * prior
        + 0.8 * is_b  # risk the features do not explain
    )
    default = (rng.random(n_rows) < 1 / (1 + np.exp(-logit))).astype("int64")
    return pd.DataFrame(
        {
            "income": income,
            "debt_ratio": debt_ratio,
            "years_employed": years.astype("int64"),
            "prior_defaults": prior.astype("int64"),
            GROUP: group,
            LABEL: default,
        }
    )


def split_frame(df: pd.DataFrame, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Shuffle (seeded) and split 50% train / 25% validation / 25% test."""
    order = np.random.default_rng(seed).permutation(len(df))
    a, b = len(df) // 2, (3 * len(df)) // 4
    return df.iloc[order[:a]], df.iloc[order[a:b]], df.iloc[order[b:]]


def train_reference_model(train: pd.DataFrame, seed: int = 0) -> Pipeline:
    """Fit the model under evaluation: scaling + logistic regression on FEATURES (not the group)."""
    model = Pipeline(
        [("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1000, random_state=seed))]
    )
    return model.fit(train[list(FEATURES)], train[LABEL])


def predict_scores(model: Any, df: pd.DataFrame) -> np.ndarray:
    """P(default) for each row."""
    return model.predict_proba(df[list(FEATURES)])[:, 1]


def to_markdown_table(df: pd.DataFrame, digits: int = 3) -> str:
    """Render a DataFrame (with its index) as a Markdown table; floats get ``digits`` decimals."""
    header = [str(df.index.name or ""), *map(str, df.columns)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for idx, *values in df.itertuples(name=None):
        cells = [str(idx)]
        for v in values:
            if isinstance(v, float | np.floating):
                cells.append("n/a" if math.isnan(v) else f"{v:.{digits}f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _as_arrays(y_true: Sequence[int], y_other: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    yt, yo = np.asarray(y_true, dtype=int), np.asarray(y_other, dtype=float)
    if yt.shape != yo.shape or yt.ndim != 1:
        raise ValueError(f"inputs must be 1-D and the same length, got {yt.shape} and {yo.shape}")
    if not np.isin(yt, (0, 1)).all():
        raise ValueError("y_true must contain only 0 and 1")
    return yt, yo


# ---------------------------------------------------------------------------
# Milestone 1: save and load a model with an integrity check
# ---------------------------------------------------------------------------


class IntegrityError(ValueError):
    """The model file does not match its recorded SHA-256 digest."""


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def checksum_path(model_path: Path | str) -> Path:
    """Where the digest of ``model_path`` is stored: ``<file>.sha256`` next to it."""
    path = Path(model_path)
    return path.with_name(path.name + ".sha256")


def save_model(model: Any, path: Path | str) -> str:
    """Pickle ``model`` to ``path`` and write its SHA-256 to ``<path>.sha256``.

    The checksum file uses the ``sha256sum`` format (``<digest>  <file name>``), so it can also be
    checked with standard tools.

    Returns:
        The hex digest.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(data)
    digest = sha256_bytes(data)
    checksum_path(path).write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def load_model(path: Path | str, expected_sha256: str | None = None) -> Any:
    """Load a pickled model only if its bytes match the expected SHA-256.

    Security: unpickling runs code chosen by whoever wrote the file. **Only load models you trust.**
    The digest check detects corruption or tampering *after* the digest was recorded — store the
    digest somewhere the model file's writer cannot change (a registry, a signed manifest).

    Args:
        path: The model file.
        expected_sha256: The trusted digest; defaults to the one in ``<path>.sha256``.

    Raises:
        IntegrityError: if no digest is available or the file does not match it.
    """
    path = Path(path)
    if expected_sha256 is None:
        sidecar = checksum_path(path)
        if not sidecar.exists():
            raise IntegrityError(f"no checksum for {path.name}: refusing to unpickle an unverified file")
        expected_sha256 = sidecar.read_text(encoding="utf-8").split()[0]
    data = path.read_bytes()  # hash and unpickle the *same* bytes (no check-then-reread race)
    actual = sha256_bytes(data)
    if not hmac.compare_digest(actual, expected_sha256.strip().lower()):
        raise IntegrityError(
            f"{path.name}: SHA-256 {actual[:12]}... does not match {expected_sha256[:12]}..."
        )
    return pickle.loads(data)  # noqa: S301 - integrity verified above; only load models you trust


# ---------------------------------------------------------------------------
# Milestone 2: slice metrics, confusion matrices and fairness gaps
# ---------------------------------------------------------------------------


def confusion_counts(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    """Counts of true negatives, false positives, false negatives and true positives."""
    yt, yp = _as_arrays(y_true, y_pred)
    yp = yp.astype(int)
    return {
        "tn": int(((yt == 0) & (yp == 0)).sum()),
        "fp": int(((yt == 0) & (yp == 1)).sum()),
        "fn": int(((yt == 1) & (yp == 0)).sum()),
        "tp": int(((yt == 1) & (yp == 1)).sum()),
    }


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else float("nan")


def rates(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float]:
    """Rates for one slice: n, base_rate, selection_rate, tpr, fpr, precision, accuracy.

    Undefined rates (for example TPR in a slice with no positives) are NaN, not 0.
    """
    c = confusion_counts(y_true, y_pred)
    n = sum(c.values())
    return {
        "n": float(n),
        "base_rate": _ratio(c["tp"] + c["fn"], n),
        "selection_rate": _ratio(c["tp"] + c["fp"], n),
        "tpr": _ratio(c["tp"], c["tp"] + c["fn"]),
        "fpr": _ratio(c["fp"], c["fp"] + c["tn"]),
        "precision": _ratio(c["tp"], c["tp"] + c["fp"]),
        "accuracy": _ratio(c["tp"] + c["tn"], n),
    }


def slice_metrics(
    y_true: Sequence[int], y_score: Sequence[float], groups: Sequence[str], threshold: float = 0.5
) -> pd.DataFrame:
    """Metrics per group plus an ``overall`` row, at one decision threshold (score >= threshold).

    Returns:
        Index: sorted group names then ``"overall"``; columns as in :func:`rates`, ``n`` as int.
    """
    yt, ys = _as_arrays(y_true, y_score)
    g = np.asarray(groups).astype(str)
    if g.shape != yt.shape:
        raise ValueError("groups must have one entry per row")
    pred = (ys >= threshold).astype(int)
    rows = {name: rates(yt[g == name], pred[g == name]) for name in sorted(set(g))}
    rows["overall"] = rates(yt, pred)
    table = pd.DataFrame.from_dict(rows, orient="index")
    table["n"] = table["n"].astype("int64")
    table.index.name = "group"
    return table


def confusion_matrices(
    y_true: Sequence[int], y_score: Sequence[float], groups: Sequence[str], threshold: float = 0.5
) -> dict[str, np.ndarray]:
    """2x2 confusion matrix ``[[tn, fp], [fn, tp]]`` per group and ``overall`` (scikit-learn layout)."""
    yt, ys = _as_arrays(y_true, y_score)
    g = np.asarray(groups).astype(str)
    pred = (ys >= threshold).astype(int)
    out = {}
    for name in [*sorted(set(g)), "overall"]:
        mask = np.ones_like(yt, dtype=bool) if name == "overall" else g == name
        c = confusion_counts(yt[mask], pred[mask])
        out[name] = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
    return out


def fairness_gaps(slices: pd.DataFrame) -> dict[str, float]:
    """Between-group gaps computed from :func:`slice_metrics` (the ``overall`` row is ignored).

    * ``demographic_parity_difference``: max − min selection rate.
    * ``disparate_impact_ratio``: min / max selection rate (the "80% rule" compares it with 0.8).
    * ``equal_opportunity_difference``: max − min true-positive rate.
    * ``fpr_difference``: max − min false-positive rate (people wrongly flagged).
    * ``equalized_odds_difference``: the larger of the TPR and FPR differences.
    * ``accuracy_difference``: max − min accuracy.
    """
    groups = slices.drop(index="overall", errors="ignore")
    if len(groups) < 2:
        raise ValueError("need at least two groups to compare")

    def spread(col: str) -> float:
        return float(groups[col].max() - groups[col].min())

    sel = groups["selection_rate"]
    tpr_gap, fpr_gap = spread("tpr"), spread("fpr")
    return {
        "demographic_parity_difference": spread("selection_rate"),
        "disparate_impact_ratio": _ratio(float(sel.min()), float(sel.max())),
        "equal_opportunity_difference": tpr_gap,
        "fpr_difference": fpr_gap,
        "equalized_odds_difference": max(tpr_gap, fpr_gap),
        "accuracy_difference": spread("accuracy"),
    }


# ---------------------------------------------------------------------------
# Milestone 3: calibration
# ---------------------------------------------------------------------------


def calibration_table(y_true: Sequence[int], y_prob: Sequence[float], n_bins: int = 10) -> pd.DataFrame:
    """Reliability table with equal-width bins over [0, 1].

    Bin ``i`` holds probabilities in ``[i/n_bins, (i+1)/n_bins)``; the last bin also includes 1.0.
    Empty bins are left out.

    Returns:
        Columns ``bin, lower, upper, count, mean_predicted, fraction_positive, gap`` where
        ``gap = mean_predicted - fraction_positive`` (positive = over-confident).
    """
    yt, yp = _as_arrays(y_true, y_prob)
    if n_bins < 1:
        raise ValueError(f"n_bins must be at least 1, got {n_bins}")
    if ((yp < 0) | (yp > 1)).any():
        raise ValueError("probabilities must be within [0, 1]")
    idx = np.minimum((yp * n_bins).astype(int), n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        mean_pred, frac = float(yp[mask].mean()), float(yt[mask].mean())
        rows.append(
            {
                "bin": b,
                "lower": b / n_bins,
                "upper": (b + 1) / n_bins,
                "count": int(mask.sum()),
                "mean_predicted": mean_pred,
                "fraction_positive": frac,
                "gap": mean_pred - frac,
            }
        )
    return pd.DataFrame(
        rows, columns=["bin", "lower", "upper", "count", "mean_predicted", "fraction_positive", "gap"]
    )


def brier_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """Mean squared difference between predicted probability and outcome (0 is perfect)."""
    yt, yp = _as_arrays(y_true, y_prob)
    return float(np.mean((yp - yt) ** 2))


def expected_calibration_error(y_true: Sequence[int], y_prob: Sequence[float], n_bins: int = 10) -> float:
    """ECE: the count-weighted mean of ``|gap|`` over the bins of :func:`calibration_table`."""
    table = calibration_table(y_true, y_prob, n_bins)
    return float((table["count"] * table["gap"].abs()).sum() / table["count"].sum())


def calibration_by_group(
    y_true: Sequence[int], y_prob: Sequence[float], groups: Sequence[str], n_bins: int = 10
) -> pd.DataFrame:
    """Per-group calibration: ``n, mean_predicted, observed_rate, brier, ece`` (index = group)."""
    yt, yp = _as_arrays(y_true, y_prob)
    g = np.asarray(groups).astype(str)
    rows = {}
    for name in sorted(set(g)):
        m = g == name
        rows[name] = {
            "n": int(m.sum()),
            "mean_predicted": float(yp[m].mean()),
            "observed_rate": float(yt[m].mean()),
            "brier": brier_score(yt[m], yp[m]),
            "ece": expected_calibration_error(yt[m], yp[m], n_bins),
        }
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "group"
    return table


# ---------------------------------------------------------------------------
# Milestone 4: choose the threshold by expected cost
# ---------------------------------------------------------------------------


def _check_costs(cost_fp: float, cost_fn: float) -> None:
    if cost_fp < 0 or cost_fn < 0 or cost_fp + cost_fn == 0:
        raise ValueError(f"costs must be non-negative and not both zero, got fp={cost_fp}, fn={cost_fn}")


def expected_cost(
    y_true: Sequence[int], y_prob: Sequence[float], threshold: float, cost_fp: float, cost_fn: float
) -> float:
    """Average cost per decision: ``(FP * cost_fp + FN * cost_fn) / n`` at ``threshold``."""
    _check_costs(cost_fp, cost_fn)
    yt, yp = _as_arrays(y_true, y_prob)
    c = confusion_counts(yt, (yp >= threshold).astype(int))
    return (c["fp"] * cost_fp + c["fn"] * cost_fn) / len(yt)


def default_thresholds() -> np.ndarray:
    """0.00, 0.01, ..., 1.00."""
    return np.round(np.linspace(0.0, 1.0, 101), 2)


def cost_curve(
    y_true: Sequence[int],
    y_prob: Sequence[float],
    cost_fp: float,
    cost_fn: float,
    thresholds: Sequence[float] | None = None,
) -> pd.DataFrame:
    """Expected cost at each candidate threshold: columns ``threshold, fp, fn, cost`` (sorted)."""
    _check_costs(cost_fp, cost_fn)
    yt, yp = _as_arrays(y_true, y_prob)
    candidates = sorted(set(map(float, default_thresholds() if thresholds is None else thresholds)))
    if not candidates:
        raise ValueError("give at least one threshold")
    rows = []
    for t in candidates:
        c = confusion_counts(yt, (yp >= t).astype(int))
        rows.append(
            {
                "threshold": t,
                "fp": c["fp"],
                "fn": c["fn"],
                "cost": (c["fp"] * cost_fp + c["fn"] * cost_fn) / len(yt),
            }
        )
    return pd.DataFrame(rows)


def select_threshold(
    y_true: Sequence[int],
    y_prob: Sequence[float],
    cost_fp: float,
    cost_fn: float,
    thresholds: Sequence[float] | None = None,
) -> tuple[float, float]:
    """The threshold with the lowest expected cost (the smallest such threshold if tied).

    Choose it on *validation* data and report its cost on *test* data, or the reported cost will be
    optimistic.

    Returns:
        ``(threshold, cost)``.
    """
    curve = cost_curve(y_true, y_prob, cost_fp, cost_fn, thresholds)
    best = curve.loc[curve["cost"].idxmin()]  # idxmin returns the first (smallest) threshold among ties
    return float(best["threshold"]), float(best["cost"])


def bayes_threshold(cost_fp: float, cost_fn: float) -> float:
    """For *calibrated* probabilities, flagging when ``p >= cost_fp / (cost_fp + cost_fn)`` minimises cost."""
    _check_costs(cost_fp, cost_fn)
    return cost_fp / (cost_fp + cost_fn)


# ---------------------------------------------------------------------------
# Milestone 5: evaluate a saved model and write the report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationResult:
    """Everything the report needs."""

    model_sha256: str
    n_validation: int
    n_test: int
    cost_fp: float
    cost_fn: float
    threshold: float
    cost_at_threshold: float
    cost_at_default: float
    slices: pd.DataFrame
    gaps: dict[str, float]
    confusion: dict[str, np.ndarray]
    calibration: pd.DataFrame
    calibration_groups: pd.DataFrame
    brier: float
    ece: float


def evaluate_saved_model(
    model_path: Path | str,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    cost_fp: float = 1.0,
    cost_fn: float = 5.0,
    n_bins: int = 10,
) -> EvaluationResult:
    """Load the model (integrity-checked), choose the threshold on validation, evaluate on test."""
    model = load_model(model_path)
    digest = checksum_path(model_path).read_text(encoding="utf-8").split()[0]
    threshold, _ = select_threshold(validation[LABEL], predict_scores(model, validation), cost_fp, cost_fn)
    y, p, g = test[LABEL].to_numpy(), predict_scores(model, test), test[GROUP].to_numpy()
    return EvaluationResult(
        model_sha256=digest,
        n_validation=len(validation),
        n_test=len(test),
        cost_fp=cost_fp,
        cost_fn=cost_fn,
        threshold=threshold,
        cost_at_threshold=expected_cost(y, p, threshold, cost_fp, cost_fn),
        cost_at_default=expected_cost(y, p, 0.5, cost_fp, cost_fn),
        slices=slice_metrics(y, p, g, threshold),
        gaps=fairness_gaps(slice_metrics(y, p, g, threshold)),
        confusion=confusion_matrices(y, p, g, threshold),
        calibration=calibration_table(y, p, n_bins),
        calibration_groups=calibration_by_group(y, p, g, n_bins),
        brier=brier_score(y, p),
        ece=expected_calibration_error(y, p, n_bins),
    )


def render_report(result: EvaluationResult, tolerance: float = 0.1) -> str:
    """Markdown report. Gaps above ``tolerance`` (and a disparate-impact ratio below 0.8) are flagged."""
    gap_lines = []
    for name, value in result.gaps.items():
        flagged = value < 0.8 if name == "disparate_impact_ratio" else value > tolerance
        gap_lines.append(f"| {name} | {value:.3f} | {'**review**' if flagged else 'ok'} |")
    matrices = []
    for name, m in result.confusion.items():
        matrices += [
            f"**{name}**",
            "",
            "| | predicted 0 | predicted 1 |",
            "|---|---|---|",
            f"| actual 0 | {m[0, 0]} | {m[0, 1]} |",
            f"| actual 1 | {m[1, 0]} | {m[1, 1]} |",
            "",
        ]
    calibration_lines = []
    for gname, row in result.calibration_groups.iterrows():
        diff = row["mean_predicted"] - row["observed_rate"]
        direction = "over-predicts" if diff > 0 else "under-predicts"
        calibration_lines.append(
            f"- Group **{gname}**: mean predicted risk {row['mean_predicted']:.3f} vs observed default rate "
            f"{row['observed_rate']:.3f} — the model {direction} risk by {abs(diff):.3f}."
        )
    parts = [
        "# Model evaluation report",
        "",
        "## Summary",
        f"- Model file SHA-256: `{result.model_sha256}`",
        f"- Threshold chosen on validation ({result.n_validation} rows) for costs FP = {result.cost_fp:g}, "
        f"FN = {result.cost_fn:g}: **{result.threshold:.2f}**",
        f"- Test set: {result.n_test} rows. Expected cost per decision: "
        f"{result.cost_at_threshold:.3f} at the chosen threshold vs {result.cost_at_default:.3f} at 0.5.",
        f"- Brier score {result.brier:.3f}, expected calibration error {result.ece:.3f}.",
        "",
        "## Performance by group",
        to_markdown_table(result.slices),
        "",
        "## Fairness gaps",
        f"Differences between groups at threshold {result.threshold:.2f} (tolerance {tolerance:g}).",
        "",
        "| metric | value | status |",
        "|---|---|---|",
        *gap_lines,
        "",
        "## Confusion matrices",
        "",
        *matrices,
        "## Calibration",
        to_markdown_table(result.calibration.set_index("bin")),
        "",
        "Calibration by group:",
        "",
        to_markdown_table(result.calibration_groups),
        "",
        *calibration_lines,
        "",
        "## Threshold selection",
        f"Flagging costs {result.cost_fp:g} per false positive and {result.cost_fn:g} per false negative, "
        f"so the cost-minimising threshold is {result.threshold:.2f} instead of 0.5.",
        "",
        "## Limitations",
        "- Synthetic data: the groups and effects are invented to make the evaluation visible.",
        "- Group metrics on small groups are noisy; report counts and confidence intervals before acting.",
        "- Fairness metrics conflict: equal selection rates and equal error rates cannot both hold when "
        "base rates differ. Choosing which gap matters is a policy decision, not a technical one.",
        "",
    ]
    return "\n".join(parts)


def write_report(result: EvaluationResult, path: Path | str, tolerance: float = 0.1) -> Path:
    """Write :func:`render_report` to ``path`` (UTF-8), creating parent folders."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(result, tolerance), encoding="utf-8")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Generate data, train and save the reference model, evaluate it and write the report."""
    parser = argparse.ArgumentParser(description="Evaluate a saved model by group, calibration and cost.")
    parser.add_argument("--out-dir", type=Path, default=Path("evaluation"))
    parser.add_argument("--cost-fp", type=float, default=1.0)
    parser.add_argument("--cost-fn", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    train, validation, test = split_frame(make_applicants(seed=args.seed), seed=args.seed)
    model_path = args.out_dir / "model.pkl"
    save_model(train_reference_model(train, seed=args.seed), model_path)
    result = evaluate_saved_model(model_path, validation, test, args.cost_fp, args.cost_fn)
    report = write_report(result, args.out_dir / "report.md")
    print(f"Model saved to {model_path}; report written to {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
