"""Train, select and evaluate a classifier without leaking the test set (starter).

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
    # TODO: data = load_breast_cancer(as_frame=True); X = data.data.
    # TODO: flip the target so 1 = malignant: y = (1 - data.target), as int64, renamed "malignant".
    raise NotImplementedError("TODO: implement load_data()")


def split_data(
    X: pd.DataFrame, y: pd.Series, val_size: float = 0.2, test_size: float = 0.2, seed: int = 42
) -> Splits:
    """Split into train / validation / test, stratified by class and seeded.

    The test set is carved off first, then the validation set from what remains, so that
    ``val_size`` and ``test_size`` are fractions of the *whole* dataset.

    Raises:
        ValueError: if the sizes are not positive or leave no training data.
    """
    # TODO: validate the sizes and that X and y have the same length (ValueError).
    # TODO: 1) train_test_split(X, y, test_size=test_size, stratify=y, random_state=seed) -> rest / test.
    # TODO: 2) split rest again with test_size=val_size / (1 - test_size), stratify=y_rest, same seed.
    # TODO: return Splits(X_train, X_val, X_test, y_train, y_val, y_test).
    raise NotImplementedError("TODO: implement split_data()")


# ---------------------------------------------------------------------------
# Milestone 2: pipeline and baseline
# ---------------------------------------------------------------------------


def build_pipeline(C: float = 1.0, seed: int = 42) -> Pipeline:
    """Scaling + logistic regression in one Pipeline.

    Because the scaler lives *inside* the pipeline, ``fit`` learns its means and standard deviations
    from whatever data the pipeline is fitted on — the training split only — and ``predict`` reuses
    them. Scaling the whole dataset before splitting would leak test-set statistics into training.
    """
    # TODO: raise ValueError if C <= 0.
    # TODO: return Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(C=C, max_iter=5000,
    #   random_state=seed))]). The step names matter: the tests look up named_steps["scaler"].
    raise NotImplementedError("TODO: implement build_pipeline()")


def build_baseline() -> DummyClassifier:
    """A model that ignores the features and predicts class frequencies (the bar to beat)."""
    # TODO: DummyClassifier(strategy="prior"): predicts the majority class, probabilities = class shares.
    raise NotImplementedError("TODO: implement build_baseline()")


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
    # TODO: raise ValueError unless 0 <= threshold <= 1.
    # TODO: scores = positive_scores(model, X); pred = (scores >= threshold).astype(int).
    # TODO: precision/recall/f1 with zero_division=0; roc_auc_score(y, scores) uses the scores, not pred.
    # TODO: return plain floats.
    raise NotImplementedError("TODO: implement evaluate()")


def compare_models(models: Mapping[str, ClassifierMixin], splits: Splits) -> pd.DataFrame:
    """Fit a fresh copy of each model on the training split and score it on the validation split.

    The models passed in are not modified (each is cloned before fitting).

    Returns:
        One row per model name, columns :data:`METRICS`, sorted by ROC-AUC (best first).
    """
    # TODO: for each model: clone(model).fit(train) — never fit the caller's object — then evaluate on val.
    # TODO: build a DataFrame (index = names, columns = list(METRICS)) sorted by roc_auc, best first.
    raise NotImplementedError("TODO: implement compare_models()")


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
    # TODO: validate metric and cs (ValueError).
    # TODO: for each C in sorted(cs): fit build_pipeline(C, seed) on train, evaluate on VALIDATION.
    # TODO: table index = C (named "C"), columns METRICS; best = table[metric].idxmax() (first = smallest C).
    # TODO: do not use splits.X_test or splits.y_test anywhere in this function.
    raise NotImplementedError("TODO: implement select_c()")


def train_final(splits: Splits, c: float, seed: int = 42) -> Pipeline:
    """Fit the chosen pipeline on the training split."""
    # TODO: fit build_pipeline(C=c, seed=seed) on the training split and return it.
    raise NotImplementedError("TODO: implement train_final()")


def final_report(model: Any, baseline: Any, splits: Splits) -> pd.DataFrame:
    """Test-set metrics for the chosen model and the (train-fitted) baseline — computed once, at the end."""
    # TODO: evaluate both models on the TEST split; return a DataFrame with rows "model" and "baseline"
    #   and columns list(METRICS).
    raise NotImplementedError("TODO: implement final_report()")


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
