"""Evaluate a saved model beyond one accuracy number (starter).

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
    # TODO: create the parent folder; data = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL); write
    #   the bytes.
    # TODO: digest = sha256_bytes(data); write f"{digest}  {path.name}\n" to checksum_path(path); return
    #   digest.
    raise NotImplementedError("TODO: implement save_model()")


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
    # TODO: expected digest: the argument, or the first word of the .sha256 file; if neither exists raise
    #   IntegrityError.
    # TODO: read the bytes ONCE, hash those bytes, compare with hmac.compare_digest (lower-case both),
    #   raise IntegrityError on mismatch, and only then return pickle.loads(data) (silence ruff S301 with a
    #   noqa comment that says why).
    raise NotImplementedError("TODO: implement load_model()")


# ---------------------------------------------------------------------------
# Milestone 2: slice metrics, confusion matrices and fairness gaps
# ---------------------------------------------------------------------------


def confusion_counts(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    """Counts of true negatives, false positives, false negatives and true positives."""
    # TODO: yt, yp = _as_arrays(y_true, y_pred) (validates lengths and 0/1 labels).
    # TODO: count tn, fp, fn, tp with boolean masks; return plain ints.
    raise NotImplementedError("TODO: implement confusion_counts()")


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else float("nan")


def rates(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, float]:
    """Rates for one slice: n, base_rate, selection_rate, tpr, fpr, precision, accuracy.

    Undefined rates (for example TPR in a slice with no positives) are NaN, not 0.
    """
    # TODO: use confusion_counts; n = total. base_rate = (tp+fn)/n, selection_rate = (tp+fp)/n,
    #   tpr = tp/(tp+fn), fpr = fp/(fp+tn), precision = tp/(tp+fp), accuracy = (tp+tn)/n.
    # TODO: use _ratio() so a zero denominator gives NaN (undefined), never 0 or ZeroDivisionError.
    raise NotImplementedError("TODO: implement rates()")


def slice_metrics(
    y_true: Sequence[int], y_score: Sequence[float], groups: Sequence[str], threshold: float = 0.5
) -> pd.DataFrame:
    """Metrics per group plus an ``overall`` row, at one decision threshold (score >= threshold).

    Returns:
        Index: sorted group names then ``"overall"``; columns as in :func:`rates`, ``n`` as int.
    """
    # TODO: pred = (score >= threshold). One row per sorted group name (rates of that group's rows),
    #   then an "overall" row. Index name "group"; make the n column int64.
    raise NotImplementedError("TODO: implement slice_metrics()")


def confusion_matrices(
    y_true: Sequence[int], y_score: Sequence[float], groups: Sequence[str], threshold: float = 0.5
) -> dict[str, np.ndarray]:
    """2x2 confusion matrix ``[[tn, fp], [fn, tp]]`` per group and ``overall`` (scikit-learn layout)."""
    # TODO: for each sorted group and "overall": np.array([[tn, fp], [fn, tp]]).
    raise NotImplementedError("TODO: implement confusion_matrices()")


def fairness_gaps(slices: pd.DataFrame) -> dict[str, float]:
    """Between-group gaps computed from :func:`slice_metrics` (the ``overall`` row is ignored).

    * ``demographic_parity_difference``: max − min selection rate.
    * ``disparate_impact_ratio``: min / max selection rate (the "80% rule" compares it with 0.8).
    * ``equal_opportunity_difference``: max − min true-positive rate.
    * ``fpr_difference``: max − min false-positive rate (people wrongly flagged).
    * ``equalized_odds_difference``: the larger of the TPR and FPR differences.
    * ``accuracy_difference``: max − min accuracy.
    """
    # TODO: drop the "overall" row; raise ValueError if fewer than two groups remain.
    # TODO: differences are max - min across groups (selection_rate, tpr, fpr, accuracy);
    #   disparate_impact_ratio = min / max selection rate; equalized_odds = max(tpr gap, fpr gap).
    raise NotImplementedError("TODO: implement fairness_gaps()")


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
    # TODO: validate n_bins >= 1 and 0 <= p <= 1 (ValueError).
    # TODO: bin index = min(int(p * n_bins), n_bins - 1) so that 1.0 lands in the last bin.
    # TODO: for each non-empty bin: bin, lower, upper, count, mean_predicted, fraction_positive,
    #   gap = mean_predicted - fraction_positive.
    raise NotImplementedError("TODO: implement calibration_table()")


def brier_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """Mean squared difference between predicted probability and outcome (0 is perfect)."""
    # TODO: mean((p - y) ** 2).
    raise NotImplementedError("TODO: implement brier_score()")


def expected_calibration_error(y_true: Sequence[int], y_prob: Sequence[float], n_bins: int = 10) -> float:
    """ECE: the count-weighted mean of ``|gap|`` over the bins of :func:`calibration_table`."""
    # TODO: sum(count * |gap|) / sum(count) over calibration_table(...).
    raise NotImplementedError("TODO: implement expected_calibration_error()")


def calibration_by_group(
    y_true: Sequence[int], y_prob: Sequence[float], groups: Sequence[str], n_bins: int = 10
) -> pd.DataFrame:
    """Per-group calibration: ``n, mean_predicted, observed_rate, brier, ece`` (index = group)."""
    # TODO: per sorted group: n, mean_predicted, observed_rate, brier, ece. Index name "group".
    raise NotImplementedError("TODO: implement calibration_by_group()")


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
    # TODO: _check_costs; predictions = p >= threshold; (fp * cost_fp + fn * cost_fn) / n.
    raise NotImplementedError("TODO: implement expected_cost()")


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
    # TODO: candidates: default_thresholds() or the given ones, de-duplicated and sorted (ValueError if
    #   empty).
    # TODO: one row per threshold: threshold, fp, fn, cost (average cost per decision).
    raise NotImplementedError("TODO: implement cost_curve()")


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
    # TODO: the row of cost_curve with the minimum cost; idxmin() gives the smallest threshold among ties.
    # TODO: return (threshold, cost) as floats.
    raise NotImplementedError("TODO: implement select_threshold()")


def bayes_threshold(cost_fp: float, cost_fn: float) -> float:
    """For *calibrated* probabilities, flagging when ``p >= cost_fp / (cost_fp + cost_fn)`` minimises cost."""
    # TODO: _check_costs, then cost_fp / (cost_fp + cost_fn).
    raise NotImplementedError("TODO: implement bayes_threshold()")


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
    # TODO: model = load_model(model_path) (integrity-checked); digest from checksum_path(model_path).
    # TODO: choose the threshold on VALIDATION with select_threshold; compute everything else on TEST:
    #   costs at the chosen threshold and at 0.5, slices, gaps, confusion matrices, calibration table,
    #   calibration by group, Brier and ECE. Return an EvaluationResult.
    raise NotImplementedError("TODO: implement evaluate_saved_model()")


def render_report(result: EvaluationResult, tolerance: float = 0.1) -> str:
    """Markdown report. Gaps above ``tolerance`` (and a disparate-impact ratio below 0.8) are flagged."""
    # TODO: Markdown with sections: # Model evaluation report, ## Summary (digest, threshold in **bold**
    #   with
    #   2 decimals, costs, Brier, ECE), ## Performance by group (to_markdown_table(result.slices)),
    #   ## Fairness gaps (a | metric | value | status | table; status **review** when a gap > tolerance
    #   or the disparate-impact ratio < 0.8), ## Confusion matrices, ## Calibration (overall table and
    #   per-group sentences: over- or under-predicts and by how much), ## Threshold selection, ##
    #   Limitations.
    raise NotImplementedError("TODO: implement render_report()")


def write_report(result: EvaluationResult, path: Path | str, tolerance: float = 0.1) -> Path:
    """Write :func:`render_report` to ``path`` (UTF-8), creating parent folders."""
    # TODO: create parent folders; write render_report(result, tolerance) as UTF-8; return the Path.
    raise NotImplementedError("TODO: implement write_report()")


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
