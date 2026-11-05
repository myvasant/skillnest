"""Behaviour tests for the EDA report, grouped by milestone.

Most tests use tiny hand-made DataFrames whose answers you can work out on paper; a few check that the
analysis finds the patterns deliberately built into the seeded retail dataset.
"""

from __future__ import annotations

import math

import eda_report as eda
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def retail() -> pd.DataFrame:
    """The seeded synthetic dataset used throughout the project."""
    return eda.make_retail_data(n_rows=1000, seed=42)


@pytest.fixture
def tiny() -> pd.DataFrame:
    """Five rows you can summarise by hand."""
    return pd.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            "y": [1.0, 3.0, 2.0, 5.0, 4.0],
            "z": [2.0, 1.0, 4.0, 3.0, 6.0],
            "shop": ["a", "b", "a", "b", "a"],
        }
    )


class TestProvidedDataset:
    """The generator is provided; these tests document what it guarantees."""

    def test_same_seed_gives_identical_data(self) -> None:
        pd.testing.assert_frame_equal(eda.make_retail_data(200, seed=7), eda.make_retail_data(200, seed=7))

    def test_different_seed_gives_different_data(self) -> None:
        assert not eda.make_retail_data(200, seed=1).equals(eda.make_retail_data(200, seed=2))

    def test_columns(self, retail: pd.DataFrame) -> None:
        assert list(retail.columns) == [
            "order_id",
            "order_date",
            "region",
            "category",
            "channel",
            "units",
            "unit_price",
            "discount",
            "revenue",
            "delivery_days",
            "customer_age",
            "satisfaction",
        ]
        assert len(retail) == 1000


class TestMilestone1SummaryStatistics:
    """Milestone 1: numeric and categorical summaries."""

    def test_numeric_summary_columns_and_rows(self, tiny: pd.DataFrame) -> None:
        summary = eda.numeric_summary(tiny)
        assert list(summary.index) == ["x", "y", "z"], "one row per numeric column, in table order"
        expected = ["count", "missing", "mean", "std", "min", "q1", "median", "q3", "max"]
        assert list(summary.columns) == expected

    def test_numeric_summary_values_by_hand(self, tiny: pd.DataFrame) -> None:
        row = eda.numeric_summary(tiny).loc["x"]
        assert row["count"] == 5 and row["missing"] == 0
        assert row["mean"] == pytest.approx(3.0)
        assert row["std"] == pytest.approx(math.sqrt(2.5)), "use the sample standard deviation (ddof=1)"
        assert (row["min"], row["q1"], row["median"], row["q3"], row["max"]) == (1.0, 2.0, 3.0, 4.0, 5.0)

    def test_numeric_summary_counts_missing(self) -> None:
        df = pd.DataFrame({"a": [1.0, np.nan, 3.0, np.nan]})
        row = eda.numeric_summary(df).loc["a"]
        assert row["count"] == 2 and row["missing"] == 2
        assert row["mean"] == pytest.approx(2.0), "the mean should ignore missing values"

    def test_numeric_summary_exclude(self, retail: pd.DataFrame) -> None:
        summary = eda.numeric_summary(retail, exclude=["order_id"])
        assert "order_id" not in summary.index, "identifier columns are not measurements"
        assert {"revenue", "units", "satisfaction"} <= set(summary.index)
        assert "region" not in summary.index, "text columns belong in the categorical summary"

    def test_categorical_summary(self) -> None:
        df = pd.DataFrame({"colour": ["red", "blue", "red", None, "green"], "n": [1, 2, 3, 4, 5]})
        summary = eda.categorical_summary(df)
        assert list(summary.index) == ["colour"]
        row = summary.loc["colour"]
        assert row["count"] == 4, "count ignores missing values"
        assert row["unique"] == 3
        assert row["top"] == "red"
        assert row["top_share"] == pytest.approx(0.5)

    def test_categorical_summary_on_retail(self, retail: pd.DataFrame) -> None:
        summary = eda.categorical_summary(retail)
        assert set(summary.index) == {"region", "category", "channel"}
        assert summary.loc["region", "unique"] == 4
        assert summary.loc["channel", "unique"] == 2


class TestMilestone2MissingAndOutliers:
    """Milestone 2: missing-value report and outlier detection."""

    def test_missing_report_by_hand(self) -> None:
        df = pd.DataFrame({"a": [1, None, 3, None], "b": ["x", "y", None, "z"], "c": [1, 2, 3, 4]})
        report = eda.missing_report(df)
        assert list(report.index) == ["a", "b", "c"], "sort by number missing, worst first"
        assert list(report["n_missing"]) == [2, 1, 0]
        assert list(report["pct_missing"]) == pytest.approx([50.0, 25.0, 0.0])

    def test_missing_report_finds_the_gaps_in_retail(self, retail: pd.DataFrame) -> None:
        report = eda.missing_report(retail)
        assert set(report.index[:2]) == {"satisfaction", "customer_age"}
        assert 2 < report.loc["customer_age", "pct_missing"] < 10
        assert report.loc["revenue", "n_missing"] == 0

    def test_missing_by_group(self) -> None:
        df = pd.DataFrame({"g": ["a", "a", "b", "b", "b", "b"], "v": [1, None, 2, 3, None, None]})
        rates = eda.missing_by_group(df, "v", "g")
        assert rates.to_dict() == pytest.approx({"a": 0.5, "b": 0.5})
        df.loc[4, "v"] = 9
        assert eda.missing_by_group(df, "v", "g")["b"] == pytest.approx(0.25)

    def test_satisfaction_is_not_missing_completely_at_random(self, retail: pd.DataFrame) -> None:
        rates = eda.missing_by_group(retail, "satisfaction", "channel")
        assert rates["online"] > 2 * rates["store"], "online orders are missing satisfaction far more often"

    def test_iqr_bounds_by_hand(self) -> None:
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        # Q1 = 3.25, Q3 = 7.75 (linear interpolation), IQR = 4.5
        assert eda.iqr_bounds(s) == pytest.approx((-3.5, 14.5))
        assert eda.iqr_bounds(s, k=3.0) == pytest.approx((-10.25, 21.25))

    def test_iqr_outliers_flags_only_the_extreme_value(self) -> None:
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100, np.nan])
        mask = eda.iqr_outliers(s)
        assert mask.dtype == bool
        assert mask.tolist() == [False] * 9 + [True, False], "missing values are never outliers"

    def test_zscore_misses_what_iqr_catches_in_small_samples(self) -> None:
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        assert eda.zscore_outliers(s, threshold=3.0).sum() == 0, "100 inflates the std it is measured by"
        assert eda.zscore_outliers(s, threshold=2.5).tolist() == [False] * 9 + [True]

    def test_outlier_report(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 100], "b": list(range(10))})
        report = eda.outlier_report(df)
        assert list(report.columns) == ["lower", "upper", "n_outliers", "pct_outliers"]
        assert report.loc["a", "n_outliers"] == 1 and report.loc["b", "n_outliers"] == 0
        assert report.loc["a", "pct_outliers"] == pytest.approx(10.0)
        assert report.index[0] == "a", "most outliers first"

    def test_outlier_report_unknown_column(self, tiny: pd.DataFrame) -> None:
        with pytest.raises(KeyError):
            eda.outlier_report(tiny, ["nope"])

    def test_bulk_orders_are_flagged(self, retail: pd.DataFrame) -> None:
        mask = eda.iqr_outliers(retail["units"])
        assert retail.loc[mask, "units"].min() > retail["units"].median()
        assert retail["units"].max() in set(retail.loc[mask, "units"]), "the biggest bulk order is an outlier"


class TestMilestone3GroupComparisons:
    """Milestone 3: per-group summaries and a two-group comparison."""

    def test_group_summary_by_hand(self, tiny: pd.DataFrame) -> None:
        summary = eda.group_summary(tiny, "shop", "y")
        assert list(summary.columns) == ["count", "mean", "median", "std", "total", "share"]
        assert list(summary.index) == ["b", "a"], "sorted by mean, highest first"
        assert summary.loc["a", "count"] == 3
        assert summary.loc["a", "mean"] == pytest.approx(7 / 3)  # (1 + 2 + 4) / 3
        assert summary.loc["b", "total"] == pytest.approx(8.0)  # 3 + 5
        assert summary["share"].sum() == pytest.approx(1.0)
        assert summary.loc["a", "share"] == pytest.approx(7 / 15)

    def test_group_summary_unknown_column(self, tiny: pd.DataFrame) -> None:
        with pytest.raises(KeyError):
            eda.group_summary(tiny, "missing", "x")

    def test_compare_groups_by_hand(self) -> None:
        df = pd.DataFrame({"g": ["a"] * 3 + ["b"] * 4, "v": [1, 2, 3, 4, 5, 6, 7]})
        result = eda.compare_groups(df, "g", "v", "a", "b")
        assert result["n_a"] == 3 and result["n_b"] == 4
        assert result["mean_a"] == pytest.approx(2.0) and result["mean_b"] == pytest.approx(5.5)
        assert result["diff"] == pytest.approx(-3.5)
        # Welch: -3.5 / sqrt(1/3 + (5/3)/4) = -3.5 / sqrt(0.75)
        assert result["welch_t"] == pytest.approx(-3.5 / math.sqrt(0.75))
        # pooled variance = (2*1 + 3*5/3) / 5 = 1.4
        assert result["cohens_d"] == pytest.approx(-3.5 / math.sqrt(1.4))

    def test_compare_groups_needs_two_values_per_group(self) -> None:
        df = pd.DataFrame({"g": ["a", "b", "b"], "v": [1, 2, 3]})
        with pytest.raises(ValueError):
            eda.compare_groups(df, "g", "v", "a", "b")

    def test_retail_patterns(self, retail: pd.DataFrame) -> None:
        by_region = eda.group_summary(retail, "region", "revenue")
        assert by_region.index[0] == "West", "West orders contain more units, so the mean revenue is highest"
        sat = eda.compare_groups(retail, "channel", "satisfaction", "online", "store")
        assert sat["diff"] < -1.0 and sat["cohens_d"] < -1.0, "online satisfaction is clearly lower"


class TestMilestone4Correlation:
    """Milestone 4: correlation matrix and the strongest pairs."""

    def test_correlation_matrix(self, tiny: pd.DataFrame) -> None:
        corr = eda.correlation_matrix(tiny)
        assert list(corr.columns) == ["x", "y", "z"], "only numeric columns are correlated"
        assert corr.loc["x", "y"] == pytest.approx(0.8)
        assert np.allclose(np.diag(corr), 1.0)

    def test_unknown_method(self, tiny: pd.DataFrame) -> None:
        with pytest.raises(ValueError):
            eda.correlation_matrix(tiny, method="magic")

    def test_top_correlations_by_hand(self, tiny: pd.DataFrame) -> None:
        top = eda.top_correlations(tiny, n=3)
        assert list(top.columns) == ["var_a", "var_b", "r"]
        assert list(zip(top["var_a"], top["var_b"], strict=True)) == [("x", "z"), ("x", "y"), ("y", "z")]
        assert top["r"].tolist() == pytest.approx([10 / math.sqrt(148), 0.8, 4 / math.sqrt(148)])

    def test_top_correlations_has_no_self_or_duplicate_pairs(self, tiny: pd.DataFrame) -> None:
        top = eda.top_correlations(tiny, n=10)
        assert len(top) == 3, "3 columns give exactly 3 distinct pairs"
        assert (top["var_a"] != top["var_b"]).all()

    def test_negative_correlations_rank_by_strength(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [4, 3, 2, 1], "c": [1, 3, 2, 4]})
        top = eda.top_correlations(df, n=1)
        assert (top.loc[0, "var_a"], top.loc[0, "var_b"]) == ("a", "b")
        assert top.loc[0, "r"] == pytest.approx(-1.0), "rank by |r| but report the signed value"

    def test_spearman(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [1, 4, 9, 16, 100]})
        assert eda.top_correlations(df, method="spearman").loc[0, "r"] == pytest.approx(1.0)

    def test_retail_delivery_and_satisfaction(self, retail: pd.DataFrame) -> None:
        top = eda.top_correlations(retail, n=5, exclude=["order_id"])
        pairs = {frozenset((a, b)): r for a, b, r in top.itertuples(index=False)}
        assert pairs.get(frozenset(("delivery_days", "satisfaction")), 0) < -0.7


class TestMilestone5Findings:
    """Milestone 5: the findings dict and the written Markdown report."""

    def test_build_findings_keys(self, retail: pd.DataFrame) -> None:
        f = eda.build_findings(retail)
        keys = (
            "n_rows",
            "n_columns",
            "missing",
            "satisfaction_missing_by_channel",
            "outliers",
            "revenue",
            "revenue_by_region",
            "top_region",
            "channel_satisfaction",
            "correlations",
        )
        for key in keys:
            assert key in f, f"build_findings() should return the key {key!r}"
        assert f["n_rows"] == 1000 and f["n_columns"] == 12
        assert set(f["missing"]) == {"customer_age", "satisfaction"}, "only columns that have gaps"
        assert f["top_region"] == "West"
        assert set(f["outliers"]) == {"revenue", "units"}

    def test_findings_match_the_analysis_functions(self, retail: pd.DataFrame) -> None:
        f = eda.build_findings(retail)
        assert f["outliers"]["units"] == int(eda.iqr_outliers(retail["units"]).sum())
        expected = eda.compare_groups(retail, "channel", "satisfaction", "online", "store")
        assert f["channel_satisfaction"] == pytest.approx(expected)

    def test_render_report_sections(self, retail: pd.DataFrame) -> None:
        text = eda.render_report(eda.build_findings(retail))
        headings = ("## Data quality", "## Revenue by region", "## Strongest correlations", "## Findings")
        for heading in (*headings, "## Limitations"):
            assert heading in text, f"the report needs a {heading!r} section"
        findings_section = text.split("## Findings", 1)[1].split("## Limitations", 1)[0]
        assert "West" in findings_section, "the written findings should name the top region"
        assert "satisfaction" in findings_section
        assert "| West |" in text, "include the region table as Markdown"

    def test_write_report(self, retail: pd.DataFrame, tmp_path) -> None:
        out = eda.write_report(retail, tmp_path / "reports" / "eda.md")
        assert out.exists(), "write_report should create parent folders and the file"
        assert out.read_text(encoding="utf-8") == eda.render_report(eda.build_findings(retail))
