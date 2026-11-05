"""Behaviour tests for the model evaluation app, grouped by milestone.

Tiny hand-made arrays check each formula; the seeded synthetic loan data checks that the evaluation
surfaces the problems deliberately built into it.
"""

from __future__ import annotations

import math
from pathlib import Path

import model_evaluation as me
import numpy as np
import pandas as pd
import pytest

# Eight decisions, two groups, threshold 0.5 (worked out by hand in the comments below).
Y_TRUE = [1, 0, 1, 0, 1, 1, 0, 0]
Y_SCORE = [0.9, 0.2, 0.6, 0.7, 0.4, 0.8, 0.1, 0.3]
GROUPS = ["A", "A", "A", "A", "B", "B", "B", "B"]


@pytest.fixture(scope="module")
def loan_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return me.split_frame(me.make_applicants(n_rows=6000, seed=0), seed=0)


@pytest.fixture(scope="module")
def saved_model(loan_data, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("models") / "model.pkl"
    me.save_model(me.train_reference_model(loan_data[0], seed=0), path)
    return path


@pytest.fixture(scope="module")
def result(loan_data, saved_model: Path) -> me.EvaluationResult:
    _, validation, test = loan_data
    return me.evaluate_saved_model(saved_model, validation, test, cost_fp=1.0, cost_fn=5.0)


class TestMilestone1SaveAndLoad:
    """Milestone 1: pickle with a SHA-256 integrity check."""

    def test_round_trip(self, loan_data, tmp_path: Path) -> None:
        train, _, test = loan_data
        model = me.train_reference_model(train)
        digest = me.save_model(model, tmp_path / "m" / "model.pkl")
        assert len(digest) == 64
        sidecar = tmp_path / "m" / "model.pkl.sha256"
        assert sidecar.read_text(encoding="utf-8") == f"{digest}  model.pkl\n", "use the sha256sum format"
        loaded = me.load_model(tmp_path / "m" / "model.pkl")
        np.testing.assert_array_equal(me.predict_scores(loaded, test), me.predict_scores(model, test))

    def test_digest_matches_file_bytes(self, saved_model: Path) -> None:
        expected = me.sha256_bytes(saved_model.read_bytes())
        assert me.checksum_path(saved_model).read_text(encoding="utf-8").split()[0] == expected
        assert me.load_model(saved_model, expected_sha256=expected.upper()) is not None, (
            "hex is case-insensitive"
        )

    def test_tampered_file_is_rejected(self, saved_model: Path, tmp_path: Path) -> None:
        copy = tmp_path / "model.pkl"
        copy.write_bytes(saved_model.read_bytes() + b"\x00")
        me.checksum_path(copy).write_text(
            me.checksum_path(saved_model).read_text(encoding="utf-8"), encoding="utf-8"
        )
        with pytest.raises(me.IntegrityError):
            me.load_model(copy)

    def test_wrong_expected_digest(self, saved_model: Path) -> None:
        with pytest.raises(me.IntegrityError):
            me.load_model(saved_model, expected_sha256="0" * 64)

    def test_missing_checksum_refuses_to_load(self, saved_model: Path, tmp_path: Path) -> None:
        copy = tmp_path / "unverified.pkl"
        copy.write_bytes(saved_model.read_bytes())
        with pytest.raises(me.IntegrityError):
            me.load_model(copy)

    def test_integrity_error_is_a_value_error(self) -> None:
        assert issubclass(me.IntegrityError, ValueError)


class TestMilestone2SlicesAndFairness:
    """Milestone 2: confusion counts, per-group metrics and fairness gaps."""

    def test_confusion_counts(self) -> None:
        assert me.confusion_counts([0, 0, 1, 1, 1], [0, 1, 1, 0, 1]) == {"tn": 1, "fp": 1, "fn": 1, "tp": 2}

    def test_confusion_counts_validates_input(self) -> None:
        with pytest.raises(ValueError):
            me.confusion_counts([0, 1], [0])
        with pytest.raises(ValueError):
            me.confusion_counts([0, 2], [0, 1])

    def test_slice_metrics_by_hand(self) -> None:
        table = me.slice_metrics(Y_TRUE, Y_SCORE, GROUPS, threshold=0.5)
        assert list(table.index) == ["A", "B", "overall"]
        assert list(table.columns) == [
            "n",
            "base_rate",
            "selection_rate",
            "tpr",
            "fpr",
            "precision",
            "accuracy",
        ]
        # A: predictions [1, 0, 1, 1] -> tp 2, fp 1, fn 0, tn 1
        assert table.loc["A"].to_dict() == pytest.approx(
            {
                "n": 4,
                "base_rate": 0.5,
                "selection_rate": 0.75,
                "tpr": 1.0,
                "fpr": 0.5,
                "precision": 2 / 3,
                "accuracy": 0.75,
            }
        )
        # B: predictions [0, 1, 0, 0] -> tp 1, fp 0, fn 1, tn 2
        assert table.loc["B"].to_dict() == pytest.approx(
            {
                "n": 4,
                "base_rate": 0.5,
                "selection_rate": 0.25,
                "tpr": 0.5,
                "fpr": 0.0,
                "precision": 1.0,
                "accuracy": 0.75,
            }
        )
        assert table.loc["overall", "selection_rate"] == pytest.approx(0.5)
        assert table.loc["overall", "tpr"] == pytest.approx(0.75)

    def test_undefined_rates_are_nan(self) -> None:
        table = me.slice_metrics([0, 0, 1, 1], [0.1, 0.2, 0.9, 0.8], ["A", "A", "B", "B"])
        assert math.isnan(table.loc["A", "tpr"]), "group A has no positives, so TPR is undefined (NaN), not 0"
        assert math.isnan(table.loc["B", "fpr"])
        assert math.isnan(table.loc["A", "precision"]), "nothing predicted positive in A"

    def test_threshold_is_inclusive(self) -> None:
        table = me.slice_metrics([1, 0], [0.5, 0.49], ["A", "A"], threshold=0.5)
        assert table.loc["A", "selection_rate"] == pytest.approx(0.5), "score >= threshold is positive"

    def test_confusion_matrices(self) -> None:
        mats = me.confusion_matrices(Y_TRUE, Y_SCORE, GROUPS)
        assert set(mats) == {"A", "B", "overall"}
        np.testing.assert_array_equal(mats["A"], [[1, 1], [0, 2]])
        np.testing.assert_array_equal(mats["B"], [[2, 0], [1, 1]])
        np.testing.assert_array_equal(mats["overall"], mats["A"] + mats["B"])

    def test_fairness_gaps_by_hand(self) -> None:
        gaps = me.fairness_gaps(me.slice_metrics(Y_TRUE, Y_SCORE, GROUPS))
        assert gaps == pytest.approx(
            {
                "demographic_parity_difference": 0.5,  # 0.75 - 0.25
                "disparate_impact_ratio": 1 / 3,  # 0.25 / 0.75
                "equal_opportunity_difference": 0.5,  # TPR 1.0 vs 0.5
                "fpr_difference": 0.5,  # FPR 0.5 vs 0.0
                "equalized_odds_difference": 0.5,
                "accuracy_difference": 0.0,
            }
        )

    def test_fairness_gaps_need_two_groups(self) -> None:
        with pytest.raises(ValueError):
            me.fairness_gaps(me.slice_metrics([0, 1], [0.2, 0.8], ["A", "A"]))

    def test_loan_model_treats_groups_differently(self, loan_data, saved_model: Path) -> None:
        _, _, test = loan_data
        model = me.load_model(saved_model)
        table = me.slice_metrics(test[me.LABEL], me.predict_scores(model, test), test[me.GROUP])
        assert table.loc["B", "base_rate"] > table.loc["A", "base_rate"]
        gaps = me.fairness_gaps(table)
        assert gaps["demographic_parity_difference"] > 0.1, (
            "the model never sees the group, yet flags B far more"
        )


class TestMilestone3Calibration:
    """Milestone 3: reliability table, Brier score, ECE and calibration by group."""

    PROBS = [0.05, 0.15, 0.12, 0.95]
    LABELS = [0, 0, 1, 1]

    def test_calibration_table_by_hand(self) -> None:
        table = me.calibration_table(self.LABELS, self.PROBS, n_bins=10)
        assert list(table.columns) == [
            "bin",
            "lower",
            "upper",
            "count",
            "mean_predicted",
            "fraction_positive",
            "gap",
        ]
        assert table["bin"].tolist() == [0, 1, 9], "empty bins are left out"
        assert table["count"].tolist() == [1, 2, 1]
        assert table["mean_predicted"].tolist() == pytest.approx([0.05, 0.135, 0.95])
        assert table["fraction_positive"].tolist() == pytest.approx([0.0, 0.5, 1.0])
        assert table["gap"].tolist() == pytest.approx([0.05, -0.365, -0.05])
        assert table.loc[1, "lower"] == pytest.approx(0.1) and table.loc[1, "upper"] == pytest.approx(0.2)

    def test_bin_edges(self) -> None:
        table = me.calibration_table([0, 1, 1], [0.0, 0.1, 1.0], n_bins=10)
        assert table["bin"].tolist() == [0, 1, 9], "0.1 starts bin 1; 1.0 belongs to the last bin"

    def test_calibration_table_validates(self) -> None:
        with pytest.raises(ValueError):
            me.calibration_table([0, 1], [0.2, 1.2])
        with pytest.raises(ValueError):
            me.calibration_table([0, 1], [0.2, 0.3], n_bins=0)

    def test_brier_score_by_hand(self) -> None:
        # (0.05² + 0.15² + 0.88² + 0.05²) / 4
        assert me.brier_score(self.LABELS, self.PROBS) == pytest.approx(0.8019 / 4)
        assert me.brier_score([0, 1], [0.0, 1.0]) == 0.0

    def test_ece_by_hand(self) -> None:
        # (1 * 0.05 + 2 * 0.365 + 1 * 0.05) / 4
        assert me.expected_calibration_error(self.LABELS, self.PROBS) == pytest.approx(0.2075)

    def test_calibration_by_group(self) -> None:
        table = me.calibration_by_group(self.LABELS, self.PROBS, ["A", "A", "B", "B"])
        assert list(table.columns) == ["n", "mean_predicted", "observed_rate", "brier", "ece"]
        assert table.loc["A", "mean_predicted"] == pytest.approx(0.1)
        assert table.loc["B", "observed_rate"] == pytest.approx(1.0)

    def test_loan_model_under_predicts_group_b(self, loan_data, saved_model: Path) -> None:
        _, _, test = loan_data
        p = me.predict_scores(me.load_model(saved_model), test)
        table = me.calibration_by_group(test[me.LABEL], p, test[me.GROUP])
        assert table.loc["B", "observed_rate"] > table.loc["B", "mean_predicted"], (
            "B's extra risk is invisible"
        )
        assert table.loc["A", "mean_predicted"] > table.loc["A", "observed_rate"]
        assert me.expected_calibration_error(test[me.LABEL], p) < 0.1, "overall calibration still looks fine"


class TestMilestone4ThresholdByCost:
    """Milestone 4: expected cost and threshold selection."""

    Y = [0, 0, 1, 1]
    P = [0.1, 0.4, 0.35, 0.8]

    def test_expected_cost_by_hand(self) -> None:
        # t = 0.3 -> predictions [0, 1, 1, 1]: one false positive
        assert me.expected_cost(self.Y, self.P, 0.3, cost_fp=1, cost_fn=5) == pytest.approx(0.25)
        # t = 0.5 -> predictions [0, 0, 0, 1]: one false negative
        assert me.expected_cost(self.Y, self.P, 0.5, cost_fp=1, cost_fn=5) == pytest.approx(1.25)

    def test_select_threshold_depends_on_costs(self) -> None:
        assert me.select_threshold(self.Y, self.P, 1, 5, thresholds=[0.5, 0.3]) == pytest.approx((0.3, 0.25))
        assert me.select_threshold(self.Y, self.P, 5, 1, thresholds=[0.3, 0.5]) == pytest.approx((0.5, 0.25))

    def test_ties_pick_the_smallest_threshold(self) -> None:
        # equal costs: t = 0.3 (one false positive) and t = 0.5 (one false negative) both cost 0.25
        assert me.select_threshold(self.Y, self.P, 1, 1, thresholds=[0.5, 0.3]) == pytest.approx((0.3, 0.25))

    def test_cost_curve(self) -> None:
        curve = me.cost_curve(self.Y, self.P, 1, 5, thresholds=[0.5, 0.3])
        assert list(curve.columns) == ["threshold", "fp", "fn", "cost"]
        assert curve["threshold"].tolist() == [0.3, 0.5], "sorted thresholds"
        assert curve["cost"].tolist() == pytest.approx([0.25, 1.25])
        assert len(me.cost_curve(self.Y, self.P, 1, 5)) == 101, "default grid 0.00, 0.01, ..., 1.00"

    def test_invalid_costs(self) -> None:
        with pytest.raises(ValueError):
            me.expected_cost(self.Y, self.P, 0.5, cost_fp=-1, cost_fn=5)
        with pytest.raises(ValueError):
            me.select_threshold(self.Y, self.P, 0, 0)

    def test_bayes_threshold(self) -> None:
        assert me.bayes_threshold(1, 5) == pytest.approx(1 / 6)

    def test_selected_threshold_matches_theory_when_calibrated(self) -> None:
        rng = np.random.default_rng(1)
        p = rng.uniform(0, 1, 50_000)
        y = (rng.random(50_000) < p).astype(int)  # perfectly calibrated by construction
        threshold, _ = me.select_threshold(y, p, cost_fp=1, cost_fn=5)
        assert abs(threshold - me.bayes_threshold(1, 5)) <= 0.05

    def test_more_expensive_misses_lower_the_threshold(self, loan_data, saved_model: Path) -> None:
        _, validation, _ = loan_data
        p = me.predict_scores(me.load_model(saved_model), validation)
        t_cheap_fn, _ = me.select_threshold(validation[me.LABEL], p, cost_fp=5, cost_fn=1)
        t_dear_fn, _ = me.select_threshold(validation[me.LABEL], p, cost_fp=1, cost_fn=5)
        assert t_dear_fn < 0.5 < t_cheap_fn


class TestMilestone5Report:
    """Milestone 5: evaluate the saved model and write the Markdown report."""

    def test_result_fields(self, result: me.EvaluationResult, loan_data, saved_model: Path) -> None:
        _, validation, test = loan_data
        assert result.model_sha256 == me.sha256_bytes(saved_model.read_bytes())
        assert (result.n_validation, result.n_test) == (len(validation), len(test))
        p_val = me.predict_scores(me.load_model(saved_model), validation)
        assert result.threshold == me.select_threshold(validation[me.LABEL], p_val, 1.0, 5.0)[0], (
            "choose the threshold on validation data"
        )
        assert result.cost_at_threshold < result.cost_at_default, "the cost-based threshold beats 0.5 on test"
        assert list(result.slices.index) == ["A", "B", "overall"]
        assert set(result.confusion) == {"A", "B", "overall"}
        assert 0 < result.brier < 0.25 and 0 <= result.ece < 0.1

    def test_evaluation_refuses_tampered_models(self, loan_data, saved_model: Path, tmp_path: Path) -> None:
        _, validation, test = loan_data
        bad = tmp_path / "model.pkl"
        bad.write_bytes(saved_model.read_bytes()[:-1] + b"\x00")
        me.checksum_path(bad).write_text(
            me.checksum_path(saved_model).read_text(encoding="utf-8"), encoding="utf-8"
        )
        with pytest.raises(me.IntegrityError):
            me.evaluate_saved_model(bad, validation, test)

    def test_report_sections(self, result: me.EvaluationResult) -> None:
        text = me.render_report(result)
        for heading in (
            "# Model evaluation report",
            "## Summary",
            "## Performance by group",
            "## Fairness gaps",
            "## Confusion matrices",
            "## Calibration",
            "## Threshold selection",
            "## Limitations",
        ):
            assert heading in text, f"the report needs a {heading!r} section"
        assert result.model_sha256 in text
        assert f"**{result.threshold:.2f}**" in text
        assert "| demographic_parity_difference |" in text and "**review**" in text, "flag large gaps"

    def test_write_report(self, result: me.EvaluationResult, tmp_path: Path) -> None:
        path = me.write_report(result, tmp_path / "out" / "report.md")
        assert path.read_text(encoding="utf-8") == me.render_report(result)
