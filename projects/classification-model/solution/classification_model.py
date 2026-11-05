"""Train, select and evaluate a classifier without leaking the test set (reference solution).

Dataset: scikit-learn's bundled Breast Cancer Wisconsin (Diagnostic) data — 569 tumours, 30 numeric
features computed from images of cell nuclei. We predict ``malignant`` (1) versus benign (0).

Run the whole workflow::

    python solution/classification_model.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import ClassifierMixin, clone
from sklearn.datasets import load_breast_cancer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

METRICS: tuple[str, ...] = ("accuracy", "precision", "recall", "f1", "roc_auc")
DEFAULT_CS: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0)


@dataclass(frozen=True)
class Splits:
    """Train / validation / test partitions of the same dataset."""

    X_train: pd.DataFrame
    X_val: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series


# ---------------------------------------------------------------------------
# Milestone 1: data and splits
# ---------------------------------------------------------------------------


def load_data() -> tuple[pd.DataFrame, pd.Series]:
    """Load the breast cancer data with ``malignant`` as the positive class.

    scikit-learn encodes the target as 0 = malignant, 1 = benign. Precision and recall are about the
    *positive* class, and the clinically important class is malignant, so flip it: 1 = malignant.

    Returns:
        ``(X, y)``: 569 rows x 30 float features, and a 0/1 integer Series named ``"malignant"``.
    """
    data = load_breast_cancer(as_frame=True)
    X = data.data.copy()
    y = (1 - data.target).astype("int64").rename("malignant")
    return X, y


def split_data(
    X: pd.DataFrame, y: pd.Series, val_size: float = 0.2, test_size: float = 0.2, seed: int = 42
) -> Splits:
    """Split into train / validation / test, stratified by class and seeded.

    The test set is carved off first, then the validation set from what remains, so that
    ``val_size`` and ``test_size`` are fractions of the *whole* dataset.

    Raises:
        ValueError: if the sizes are not positive or leave no training data.
    """
    if not (0 < val_size < 1 and 0 < test_size < 1 and val_size + test_size < 1):
        raise ValueError(
            f"need 0 < val_size, test_size and val_size + test_size < 1; got {val_size}, {test_size}"
        )
    if len(X) != len(y):
        raise ValueError(f"X has {len(X)} rows but y has {len(y)}")
    X_rest, X_test, y_rest, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=seed
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_rest, y_rest, test_size=val_size / (1 - test_size), stratify=y_rest, random_state=seed
    )
    return Splits(X_train, X_val, X_test, y_train, y_val, y_test)


# ---------------------------------------------------------------------------
# Milestone 2: pipeline and baseline
# ---------------------------------------------------------------------------


def build_pipeline(C: float = 1.0, seed: int = 42) -> Pipeline:
    """Scaling + logistic regression in one Pipeline.

    Because the scaler lives *inside* the pipeline, ``fit`` learns its means and standard deviations
    from whatever data the pipeline is fitted on — the training split only — and ``predict`` reuses
    them. Scaling the whole dataset before splitting would leak test-set statistics into training.
    """
    if C <= 0:
        raise ValueError(f"C must be positive, got {C}")
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(C=C, max_iter=5000, random_state=seed)),
        ]
    )


def build_baseline() -> DummyClassifier:
    """A model that ignores the features and predicts class frequencies (the bar to beat)."""
    return DummyClassifier(strategy="prior")


# ---------------------------------------------------------------------------
# Milestone 3: metrics and comparison
# ---------------------------------------------------------------------------


def positive_scores(model: Any, X: pd.DataFrame) -> np.ndarray:
    """Predicted probability of class 1 for each row of ``X``."""
    classes = list(model.classes_)
    if 1 not in classes:
        raise ValueError(f"model was not trained with a positive class 1 (classes: {classes})")
    return model.predict_proba(X)[:, classes.index(1)]


def evaluate(model: Any, X: pd.DataFrame, y: pd.Series, threshold: float = 0.5) -> dict[str, float]:
    """Score a fitted classifier.

    Rows with ``P(malignant) >= threshold`` are predicted positive. Precision is 0 (not an error)
    when nothing is predicted positive, as for the baseline.

    Returns:
        ``{"accuracy", "precision", "recall", "f1", "roc_auc"}`` as floats. ROC-AUC uses the
        probabilities, so it does not depend on the threshold.
    """
    if not 0 <= threshold <= 1:
        raise ValueError(f"threshold must be in [0, 1], got {threshold}")
    scores = positive_scores(model, X)
    pred = (scores >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, scores)),
    }


def compare_models(models: Mapping[str, ClassifierMixin], splits: Splits) -> pd.DataFrame:
    """Fit a fresh copy of each model on the training split and score it on the validation split.

    The models passed in are not modified (each is cloned before fitting).

    Returns:
        One row per model name, columns :data:`METRICS`, sorted by ROC-AUC (best first).
    """
    rows = {}
    for name, model in models.items():
        fitted = clone(model).fit(splits.X_train, splits.y_train)
        rows[name] = evaluate(fitted, splits.X_val, splits.y_val)
    return pd.DataFrame.from_dict(rows, orient="index")[list(METRICS)].sort_values("roc_auc", ascending=False)


# ---------------------------------------------------------------------------
# Milestone 4: model selection without leakage, then one look at the test set
# ---------------------------------------------------------------------------


def select_c(
    splits: Splits, cs: Sequence[float] = DEFAULT_CS, metric: str = "f1", seed: int = 42
) -> tuple[float, pd.DataFrame]:
    """Choose the regularisation strength ``C`` using the validation split only.

    Each candidate is fitted on train and scored on validation. Ties go to the *smaller* C (the
    simpler, more regularised model). The test split is never touched.

    Returns:
        ``(best_c, table)`` where ``table`` has one row per C (index) and columns :data:`METRICS`.
    """
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}, got {metric!r}")
    if not cs:
        raise ValueError("give at least one candidate C")
    rows = {}
    for c in sorted(cs):
        model = build_pipeline(C=c, seed=seed).fit(splits.X_train, splits.y_train)
        rows[c] = evaluate(model, splits.X_val, splits.y_val)
    table = pd.DataFrame.from_dict(rows, orient="index")[list(METRICS)]
    table.index.name = "C"
    best = float(table[metric].idxmax())  # idxmax returns the first (smallest) C among ties
    return best, table


def train_final(splits: Splits, c: float, seed: int = 42) -> Pipeline:
    """Fit the chosen pipeline on the training split."""
    return build_pipeline(C=c, seed=seed).fit(splits.X_train, splits.y_train)


def final_report(model: Any, baseline: Any, splits: Splits) -> pd.DataFrame:
    """Test-set metrics for the chosen model and the (train-fitted) baseline — computed once, at the end."""
    return pd.DataFrame(
        {
            "model": evaluate(model, splits.X_test, splits.y_test),
            "baseline": evaluate(baseline, splits.X_test, splits.y_test),
        }
    ).T[list(METRICS)]


def run(seed: int = 42) -> dict[str, Any]:
    """The whole workflow: split, compare on validation, select C, train, report on test."""
    X, y = load_data()
    splits = split_data(X, y, seed=seed)
    comparison = compare_models({"baseline": build_baseline(), "logreg": build_pipeline(seed=seed)}, splits)
    best_c, table = select_c(splits, seed=seed)
    model = train_final(splits, best_c, seed=seed)
    baseline = build_baseline().fit(splits.X_train, splits.y_train)
    return {
        "splits": splits,
        "validation_comparison": comparison,
        "c_table": table,
        "best_c": best_c,
        "model": model,
        "test_report": final_report(model, baseline, splits),
    }


def main() -> int:
    """Print the validation comparison, the C search and the final test report."""
    result = run()
    print("Validation comparison:\n", result["validation_comparison"].round(3), "\n", sep="")
    print("C search (validation):\n", result["c_table"].round(3), "\n", sep="")
    print(f"Chosen C = {result['best_c']}")
    print("Test report (computed once):\n", result["test_report"].round(3), sep="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
