"""Behaviour tests for the classification workflow, grouped by milestone."""

from __future__ import annotations

import dataclasses

import classification_model as cm
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.Series]:
    return cm.load_data()


@pytest.fixture(scope="module")
def splits(data: tuple[pd.DataFrame, pd.Series]) -> cm.Splits:
    X, y = data
    return cm.split_data(X, y, val_size=0.2, test_size=0.2, seed=42)


class TestMilestone1DataAndSplits:
    """Milestone 1: positive class and seeded, stratified, disjoint splits."""

    def test_malignant_is_the_positive_class(self, data: tuple[pd.DataFrame, pd.Series]) -> None:
        X, y = data
        assert X.shape == (569, 30)
        assert y.name == "malignant"
        assert int(y.sum()) == 212, "212 of the 569 tumours are malignant; flip sklearn's 0/1 encoding"
        assert set(y.unique()) == {0, 1}

    def test_split_sizes(self, splits: cm.Splits) -> None:
        sizes = (len(splits.X_train), len(splits.X_val), len(splits.X_test))
        assert sum(sizes) == 569
        assert abs(sizes[2] - 0.2 * 569) <= 1, "test_size is a fraction of the whole dataset"
        assert abs(sizes[1] - 0.2 * 569) <= 1, "val_size is a fraction of the whole dataset too"
        assert len(splits.y_train) == sizes[0]

    def test_splits_are_disjoint(self, splits: cm.Splits) -> None:
        train, val, test = (set(s.index) for s in (splits.X_train, splits.X_val, splits.X_test))
        assert not train & val and not train & test and not val & test, "a row may appear in one split only"
        assert (splits.X_train.index == splits.y_train.index).all(), "X and y must stay aligned"

    def test_splits_are_stratified(self, splits: cm.Splits, data: tuple[pd.DataFrame, pd.Series]) -> None:
        overall = data[1].mean()
        for name in ("y_train", "y_val", "y_test"):
            rate = getattr(splits, name).mean()
            assert abs(rate - overall) < 0.02, f"{name} has {rate:.3f} malignant vs {overall:.3f} overall"

    def test_splits_are_reproducible(self, data: tuple[pd.DataFrame, pd.Series]) -> None:
        X, y = data
        a, b = cm.split_data(X, y, seed=7), cm.split_data(X, y, seed=7)
        assert list(a.X_test.index) == list(b.X_test.index)
        assert list(cm.split_data(X, y, seed=8).X_test.index) != list(a.X_test.index)

    @pytest.mark.parametrize(("val", "test"), [(0.0, 0.2), (0.5, 0.5), (0.2, 1.2)])
    def test_bad_sizes(self, data: tuple[pd.DataFrame, pd.Series], val: float, test: float) -> None:
        with pytest.raises(ValueError):
            cm.split_data(*data, val_size=val, test_size=test)


class TestMilestone2PipelineAndBaseline:
    """Milestone 2: a Pipeline that owns its preprocessing, and a baseline."""

    def test_pipeline_structure(self) -> None:
        pipe = cm.build_pipeline(C=0.5)
        assert isinstance(pipe, Pipeline)
        assert list(pipe.named_steps) == ["scaler", "model"]
        assert isinstance(pipe.named_steps["scaler"], StandardScaler)
        assert isinstance(pipe.named_steps["model"], LogisticRegression)
        assert pipe.named_steps["model"].C == 0.5

    def test_pipeline_rejects_bad_c(self) -> None:
        with pytest.raises(ValueError):
            cm.build_pipeline(C=0)

    def test_baseline_ignores_features(self, splits: cm.Splits) -> None:
        baseline = cm.build_baseline()
        assert isinstance(baseline, DummyClassifier)
        baseline.fit(splits.X_train, splits.y_train)
        proba = baseline.predict_proba(splits.X_val)
        assert np.allclose(proba, proba[0]), "the baseline gives every row the same probabilities"


class TestMilestone3Metrics:
    """Milestone 3: metrics and model comparison on the validation split."""

    def test_evaluate_on_a_hand_made_model(self) -> None:
        X = pd.DataFrame({"f": [0.0, 1.0, 2.0, 3.0]})
        y = pd.Series([0, 0, 1, 1])
        model = LogisticRegression().fit(X, y)
        metrics = cm.evaluate(model, X, y)
        assert set(metrics) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
        assert metrics["roc_auc"] == pytest.approx(1.0) and metrics["accuracy"] == pytest.approx(1.0)

    def test_threshold_trades_precision_for_recall(self, splits: cm.Splits) -> None:
        model = cm.build_pipeline().fit(splits.X_train, splits.y_train)
        low, high = (
            cm.evaluate(model, splits.X_val, splits.y_val, 0.1),
            cm.evaluate(model, splits.X_val, splits.y_val, 0.9),
        )
        assert low["recall"] >= high["recall"], "a lower threshold predicts more positives"
        assert low["precision"] <= high["precision"]
        assert low["roc_auc"] == pytest.approx(high["roc_auc"]), "ROC-AUC does not depend on the threshold"

    def test_baseline_metrics(self, splits: cm.Splits) -> None:
        baseline = cm.build_baseline().fit(splits.X_train, splits.y_train)
        metrics = cm.evaluate(baseline, splits.X_val, splits.y_val)
        assert metrics["roc_auc"] == pytest.approx(0.5)
        assert metrics["precision"] == 0.0 and metrics["recall"] == 0.0, (
            "no positives predicted: use zero_division=0"
        )
        assert metrics["accuracy"] == pytest.approx(1 - splits.y_val.mean()), "accuracy of always 'benign'"

    def test_bad_threshold(self, splits: cm.Splits) -> None:
        model = cm.build_baseline().fit(splits.X_train, splits.y_train)
        with pytest.raises(ValueError):
            cm.evaluate(model, splits.X_val, splits.y_val, threshold=1.5)

    def test_compare_models(self, splits: cm.Splits) -> None:
        models = {"baseline": cm.build_baseline(), "logreg": cm.build_pipeline()}
        table = cm.compare_models(models, splits)
        assert list(table.columns) == ["accuracy", "precision", "recall", "f1", "roc_auc"]
        assert list(table.index) == ["logreg", "baseline"], "sorted by ROC-AUC, best first"
        assert table.loc["logreg", "f1"] > table.loc["baseline", "f1"] + 0.5
        assert not hasattr(models["logreg"], "classes_"), (
            "compare_models must fit copies (sklearn.base.clone)"
        )


class TestMilestone4NoLeakageAndQualityBar:
    """Milestone 4: select on validation, fit preprocessing on train only, look at test once."""

    def test_scaler_is_fitted_on_train_only(self, splits: cm.Splits) -> None:
        model = cm.train_final(splits, c=1.0)
        scaler = model.named_steps["scaler"]
        assert np.allclose(scaler.mean_, splits.X_train.mean().to_numpy()), "scaler means must be train means"
        everything = pd.concat([splits.X_train, splits.X_val, splits.X_test])
        assert not np.allclose(scaler.mean_, everything.mean().to_numpy()), "scaler saw validation/test rows"
        assert scaler.n_samples_seen_ == len(splits.X_train)

    def test_select_c_never_touches_the_test_split(self, splits: cm.Splits) -> None:
        poisoned = dataclasses.replace(
            splits, X_test=splits.X_test * np.nan, y_test=pd.Series(np.nan, index=splits.y_test.index)
        )
        best_poisoned, _ = cm.select_c(poisoned)
        best, _ = cm.select_c(splits)
        assert best_poisoned == best, "model selection must depend on train and validation data only"

    def test_select_c_table(self, splits: cm.Splits) -> None:
        best, table = cm.select_c(splits, cs=[10.0, 0.01, 1.0])
        assert list(table.index) == [0.01, 1.0, 10.0]
        assert best in {0.01, 1.0, 10.0}
        assert table.loc[best, "f1"] == table["f1"].max()

    def test_select_c_tie_goes_to_smaller_c(self, splits: cm.Splits) -> None:
        best, table = cm.select_c(splits, cs=[1.0, 1.0 + 1e-12], metric="roc_auc")
        assert best == 1.0

    def test_select_c_validates_arguments(self, splits: cm.Splits) -> None:
        with pytest.raises(ValueError):
            cm.select_c(splits, metric="speed")
        with pytest.raises(ValueError):
            cm.select_c(splits, cs=[])

    def test_held_out_quality_bar(self, splits: cm.Splits) -> None:
        best, _ = cm.select_c(splits)
        model = cm.train_final(splits, best)
        baseline = cm.build_baseline().fit(splits.X_train, splits.y_train)
        report = cm.final_report(model, baseline, splits)
        assert list(report.index) == ["model", "baseline"]
        test = report.loc["model"]
        assert test["roc_auc"] >= 0.97, f"test ROC-AUC {test['roc_auc']:.3f} is below the 0.97 bar"
        assert test["f1"] >= 0.92, f"test F1 {test['f1']:.3f} is below the 0.92 bar"
        assert test["recall"] >= 0.90, f"test recall {test['recall']:.3f}: too many malignant tumours missed"
        assert test["roc_auc"] - report.loc["baseline", "roc_auc"] > 0.4, (
            "the model must clearly beat the baseline"
        )

    def test_run_is_deterministic(self) -> None:
        a, b = cm.run(seed=42), cm.run(seed=42)
        pd.testing.assert_frame_equal(a["test_report"], b["test_report"])
        assert a["best_c"] == b["best_c"]
