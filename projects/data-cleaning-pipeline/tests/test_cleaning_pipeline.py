"""Behaviour tests for the cleaning pipeline, grouped by milestone."""

from __future__ import annotations

import cleaning_pipeline as cp
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def raw() -> pd.DataFrame:
    """The hand-made messy export (a fresh copy for every test)."""
    return cp.raw_customers()


def text_frame(**columns: list) -> pd.DataFrame:
    """Build a DataFrame whose columns are object dtype, like a CSV read with dtype=str."""
    return pd.DataFrame({k: pd.Series(v, dtype=object) for k, v in columns.items()})


class TestMilestone1Normalise:
    """Milestone 1: column names, whitespace, placeholders and categories."""

    @pytest.mark.parametrize(
        ("raw_name", "expected"),
        [
            (" Customer ID", "customer_id"),
            ("Total Spend ($)", "total_spend"),
            ("Email ", "email"),
            ("signup-date", "signup_date"),
            ("already_clean", "already_clean"),
            ("Q1  2024 / Sales", "q1_2024_sales"),
        ],
    )
    def test_normalise_column_name(self, raw_name: str, expected: str) -> None:
        assert cp.normalise_column_name(raw_name) == expected

    def test_normalise_column_name_rejects_empty_result(self) -> None:
        with pytest.raises(ValueError):
            cp.normalise_column_name(" $$ ")

    def test_normalise_columns(self, raw: pd.DataFrame) -> None:
        out = cp.normalise_columns(raw)
        assert list(out.columns) == [
            "customer_id",
            "full_name",
            "email",
            "signup_date",
            "country",
            "age",
            "total_spend",
        ]
        assert list(raw.columns) == list(cp.RAW_COLUMNS), "do not rename the caller's DataFrame in place"

    def test_normalise_columns_refuses_collisions(self) -> None:
        df = pd.DataFrame({"Age": [1], " age ": [2]})
        with pytest.raises(ValueError, match="age"):
            cp.normalise_columns(df)

    def test_clean_text_strips_and_finds_placeholders(self) -> None:
        df = text_frame(name=["  Ada ", "n/a", "NULL", "", "  ", "Grace"], n=[1, 2, 3, 4, 5, 6])
        out = cp.clean_text(df)
        assert out.loc[0, "name"] == "Ada"
        assert out["name"].isna().tolist() == [False, True, True, True, True, False]
        assert out["n"].tolist() == [1, 2, 3, 4, 5, 6], "non-text cells are left alone"

    def test_lowercase(self) -> None:
        df = text_frame(email=["ADA@Example.com", None])
        out = cp.lowercase(df, ["email"])
        assert out.loc[0, "email"] == "ada@example.com"
        assert pd.isna(out.loc[1, "email"])

    def test_standardise_categories(self) -> None:
        df = text_frame(country=["uk", "U.K.", "United Kingdom", "GB", "usa", "Mars", None])
        mapping = {"uk": "GB", "u.k.": "GB", "united kingdom": "GB", "usa": "US"}
        out = cp.standardise_categories(df, "country", mapping)
        assert out["country"].tolist()[:6] == ["GB", "GB", "GB", "GB", "US", "Mars"]
        assert pd.isna(out.loc[6, "country"])

    def test_standardise_categories_is_idempotent(self) -> None:
        df = text_frame(country=["uk", "gb", "usa"])
        mapping = {"uk": "GB", "usa": "US"}
        once = cp.standardise_categories(df, "country", mapping)
        assert once["country"].tolist() == ["GB", "GB", "US"], "canonical values map to themselves"
        pd.testing.assert_frame_equal(cp.standardise_categories(once, "country", mapping), once)

    def test_unknown_column_is_a_key_error(self, raw: pd.DataFrame) -> None:
        with pytest.raises(KeyError):
            cp.standardise_categories(raw, "nope", {})


class TestMilestone2ParseTypes:
    """Milestone 2: dates, numbers and impossible values."""

    def test_parse_dates_tries_formats_in_order(self) -> None:
        df = text_frame(d=["2024-01-15", "15/02/2024", "March 3, 2024", "01/05/2024", "2024-13-01", None])
        out = cp.parse_dates(df, "d", ["%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y"])
        assert pd.api.types.is_datetime64_any_dtype(out["d"])
        expected = ["2024-01-15", "2024-02-15", "2024-03-03", "2024-05-01"]
        assert [str(v.date()) for v in out["d"][:4]] == expected, "01/05/2024 is 1 May with day-first"
        assert out["d"][4:].isna().all(), "unparseable or missing dates become NaT, not guesses"

    def test_parse_dates_format_order_matters(self) -> None:
        df = text_frame(d=["01/05/2024"])
        us_first = cp.parse_dates(df, "d", ["%m/%d/%Y", "%d/%m/%Y"])
        assert str(us_first.loc[0, "d"].date()) == "2024-01-05"

    def test_parse_dates_passes_datetimes_through(self) -> None:
        df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", None])})
        pd.testing.assert_frame_equal(cp.parse_dates(df, "d", ["%Y-%m-%d"]), df)

    def test_parse_dates_needs_formats(self) -> None:
        with pytest.raises(ValueError):
            cp.parse_dates(text_frame(d=["2024-01-01"]), "d", [])

    def test_parse_numbers(self) -> None:
        df = text_frame(x=["1,200.50", "$300", "1 050", "-5", "N/A", None, "abc"])
        out = cp.parse_numbers(df, "x")
        assert out["x"].dtype == float
        assert out["x"][:4].tolist() == [1200.5, 300.0, 1050.0, -5.0]
        assert out["x"][4:].isna().all()

    def test_parse_numbers_integer(self) -> None:
        df = text_frame(x=["001", " 42", "3.5", "x"])
        out = cp.parse_numbers(df, "x", integer=True)
        assert str(out["x"].dtype) == "Int64", "use pandas' nullable Int64 so missing ids are allowed"
        assert out["x"][:2].tolist() == [1, 42]
        assert out["x"][2:].isna().all(), "3.5 is not an integer id"

    def test_parse_numbers_is_idempotent(self) -> None:
        df = text_frame(x=["$1,000", "7"])
        once = cp.parse_numbers(df, "x")
        pd.testing.assert_frame_equal(cp.parse_numbers(once, "x"), once)
        ints = cp.parse_numbers(df, "x", integer=True)
        pd.testing.assert_frame_equal(cp.parse_numbers(ints, "x", integer=True), ints)

    def test_nullify_out_of_range(self) -> None:
        df = pd.DataFrame({"age": [17.0, 18.0, 45.0, 120.0, 200.0, np.nan]})
        out = cp.nullify_out_of_range(df, "age", 18, 120)
        assert out["age"].isna().tolist() == [True, False, False, False, True, True]
        assert df["age"].tolist()[:5] == [17.0, 18.0, 45.0, 120.0, 200.0], "input not modified"


class TestMilestone3Deduplicate:
    """Milestone 3: duplicates by normalised keys."""

    def test_duplicate_mask_ignores_case_and_spaces(self) -> None:
        df = text_frame(email=["ada@x.com", " ADA@x.com ", "grace@x.com", "Ada@X.com"])
        assert cp.duplicate_mask(df, ["email"]).tolist() == [False, True, False, True]
        assert cp.duplicate_mask(df, ["email"], keep="last").tolist() == [True, True, False, False]

    def test_missing_keys_are_never_duplicates(self) -> None:
        df = text_frame(email=[None, None, "a@x.com"], name=["Edsger", "Radia", "Ada"])
        assert not cp.duplicate_mask(df, ["email"]).any(), (
            "two people without an email are not the same person"
        )

    def test_composite_keys(self) -> None:
        df = text_frame(first=["Ada", "Ada", "Ada"], last=["Lovelace", "Byron", "lovelace"])
        assert cp.duplicate_mask(df, ["first", "last"]).tolist() == [False, False, True]

    def test_deduplicate_keeps_first_and_resets_index(self) -> None:
        df = text_frame(email=["b@x.com", "a@x.com", "B@x.com"], n=[1, 2, 3])
        out = cp.deduplicate(df, ["email"])
        assert out["n"].tolist() == [1, 2]
        assert list(out.index) == [0, 1]

    def test_deduplicate_needs_keys(self) -> None:
        with pytest.raises(ValueError):
            cp.deduplicate(text_frame(a=["x"]), [])


class TestMilestone4Impute:
    """Milestone 4: learn fill values, then apply them."""

    def test_fit_imputer_strategies(self) -> None:
        df = pd.DataFrame(
            {
                "age": [30.0, np.nan, 50.0, 40.0],
                "colour": ["red", "blue", None, "red"],
                "n": [1.0, 2.0, 6.0, None],
            }
        )
        fills = cp.fit_imputer(df, {"age": "median", "colour": "mode", "n": "mean"})
        assert fills == {"age": 40.0, "colour": "red", "n": 3.0}
        assert cp.fit_imputer(df, {"colour": ("constant", "unknown")}) == {"colour": "unknown"}

    def test_mode_ties_pick_the_smallest(self) -> None:
        df = text_frame(c=["b", "a", "b", "a"])
        assert cp.fit_imputer(df, {"c": "mode"}) == {"c": "a"}

    def test_fit_imputer_errors(self) -> None:
        df = pd.DataFrame({"name": ["x", None], "empty": [np.nan, np.nan]})
        with pytest.raises(ValueError):
            cp.fit_imputer(df, {"name": "median"})
        with pytest.raises(ValueError):
            cp.fit_imputer(df, {"empty": "mean"})
        with pytest.raises(ValueError):
            cp.fit_imputer(df, {"name": "magic"})
        with pytest.raises(KeyError):
            cp.fit_imputer(df, {"nope": "mode"})

    def test_apply_imputer_uses_learned_values(self) -> None:
        train = pd.DataFrame({"age": [20.0, 40.0]})
        test = pd.DataFrame({"age": [np.nan, 99.0]})
        fills = cp.fit_imputer(train, {"age": "mean"})
        assert cp.apply_imputer(test, fills)["age"].tolist() == [30.0, 99.0], "fill with the *train* mean"
        assert pd.isna(test.loc[0, "age"]), "input not modified"

    def test_impute(self) -> None:
        df = pd.DataFrame({"age": [1.0, np.nan, 3.0]})
        assert cp.impute(df, {"age": "median"})["age"].tolist() == [1.0, 2.0, 3.0]


class TestMilestone5Validate:
    """Milestone 5: schema validation and the report."""

    @pytest.fixture
    def schema(self) -> dict[str, cp.ColumnRule]:
        return {
            "id": cp.ColumnRule("integer", nullable=False, unique=True),
            "email": cp.ColumnRule("string", pattern=r"[^@\s]+@[^@\s]+\.[a-z]{2,}"),
            "age": cp.ColumnRule("number", nullable=False, min_value=18, max_value=120),
            "country": cp.ColumnRule("string", allowed=frozenset({"GB", "US"})),
        }

    def test_clean_frame_passes(self, schema: dict[str, cp.ColumnRule]) -> None:
        df = pd.DataFrame(
            {"id": [1, 2], "email": ["a@x.com", None], "age": [30.0, 40.0], "country": ["GB", "US"]}
        )
        report = cp.validate(df, schema)
        assert report.ok, report.to_markdown()
        assert report.n_rows == 2
        assert report.to_frame().empty

    def test_every_check_is_reported(self, schema: dict[str, cp.ColumnRule]) -> None:
        df = pd.DataFrame(
            {
                "id": [1, 1, 3],
                "email": ["a@x.com", "not-an-email", None],
                "age": [10.0, np.nan, 130.0],
                "country": ["GB", "FR", None],
                "extra": [0, 0, 0],
            }
        )
        report = cp.validate(df, schema)
        assert not report.ok
        assert report.failed() == {
            ("id", "unique"),
            ("email", "pattern"),
            ("age", "nullable"),
            ("age", "min"),
            ("age", "max"),
            ("country", "allowed"),
            ("extra", "unexpected_column"),
        }
        by_check = {(i.column, i.check): i for i in report.issues}
        assert by_check[("id", "unique")].rows == (0, 1), "list every row involved in a duplicate"
        assert by_check[("age", "min")].n_failed == 1 and by_check[("age", "min")].rows == (0,)
        assert by_check[("country", "allowed")].rows == (1,), "missing values are not 'not allowed'"
        assert cp.validate(df, schema, allow_extra=True).failed() >= {("id", "unique")}
        assert ("extra", "unexpected_column") not in cp.validate(df, schema, allow_extra=True).failed()

    def test_missing_column_and_wrong_kind(self, schema: dict[str, cp.ColumnRule]) -> None:
        df = pd.DataFrame({"id": ["1", "2"], "email": ["a@x.com", "b@x.com"], "age": [20.0, 30.0]})
        failed = cp.validate(df, schema).failed()
        assert ("country", "missing_column") in failed
        assert ("id", "kind") in failed, "text ids are not integers: parse them first"

    def test_report_formats(self, schema: dict[str, cp.ColumnRule]) -> None:
        df = pd.DataFrame({"id": [1, 1], "email": [None, None], "age": [20.0, 30.0], "country": ["GB", "GB"]})
        report = cp.validate(df, schema)
        frame = report.to_frame()
        assert list(frame.columns) == ["column", "check", "n_failed", "rows"]
        assert frame.loc[0, "n_failed"] == 2
        assert "unique" in report.to_markdown()


class TestMilestone6Pipeline:
    """Milestone 6: composing the steps, the log, and idempotency."""

    def test_clean_customers_result(self, raw: pd.DataFrame) -> None:
        result = cp.clean_customers(raw)
        df = result.data
        assert len(df) == 8, "Ada and Grace registered twice; keep the first registration"
        assert df["customer_id"].tolist() == [1, 2, 3, 4, 5, 6, 7, 8]
        assert df.loc[0, "full_name"] == "Ada Lovelace" and df.loc[0, "email"] == "ada@example.com"
        assert df["country"].tolist() == ["GB", "US", "GB", "US", "NL", "US", "unknown", "US"]
        assert df["total_spend"].tolist()[:6] == [1200.5, 300.0, 450.0, 75.25, -5.0, 980.0]
        # ages 200 -> missing; median of [36, 41, 52, 47, 33] = 41 fills Grace, Katherine and Edsger
        assert df["age"].tolist() == [36.0, 41.0, 41.0, 41.0, 41.0, 52.0, 47.0, 33.0]
        assert df["email"].isna().sum() == 2, "missing emails stay missing (and are not duplicates)"

    def test_validation_report_lists_what_cleaning_cannot_fix(self, raw: pd.DataFrame) -> None:
        report = cp.clean_customers(raw).report
        assert report.failed() == {("signup_date", "nullable"), ("total_spend", "min")}
        by_check = {(i.column, i.check): i.rows for i in report.issues}
        assert by_check[("signup_date", "nullable")] == (3,), "Katherine's date 2024-13-01 is invalid"
        assert by_check[("total_spend", "min")] == (4,), "a negative spend needs a human decision"

    def test_step_log(self, raw: pd.DataFrame) -> None:
        log = cp.clean_customers(raw).log
        assert [s.step for s in log] == [name for name, _ in cp.customer_steps()]
        dedupe = next(s for s in log if s.step == "deduplicate_email")
        assert (dedupe.rows_in, dedupe.rows_out) == (10, 8)
        clean = next(s for s in log if s.step == "clean_text")
        assert clean.missing_out - clean.missing_in == 6, "6 blanks/placeholders become real missing values"

    def test_idempotent(self, raw: pd.DataFrame) -> None:
        once = cp.clean_customers(raw)
        twice = cp.clean_customers(once.data)
        pd.testing.assert_frame_equal(twice.data, once.data)
        assert twice.report == once.report
        assert all(s.rows_in == s.rows_out and s.missing_in == s.missing_out for s in twice.log), (
            "on clean data no step should change anything"
        )

    def test_does_not_mutate_input(self, raw: pd.DataFrame) -> None:
        before = raw.copy()
        cp.clean_customers(raw)
        pd.testing.assert_frame_equal(raw, before)

    def test_idempotent_on_generated_data(self) -> None:
        messy = cp.make_messy_customers(n_rows=300, seed=3)
        once = cp.clean_customers(messy)
        assert len(once.data) == 300, "every injected duplicate registration is removed"
        assert once.report.ok, once.report.to_markdown()
        pd.testing.assert_frame_equal(cp.clean_customers(once.data).data, once.data)

    def test_markdown_report(self, raw: pd.DataFrame) -> None:
        text = cp.clean_customers(raw).to_markdown()
        assert "| deduplicate_email | 10 | 8 |" in text
        assert "signup_date" in text and "nullable" in text
