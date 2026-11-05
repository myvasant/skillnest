"""Behaviour tests for the expense tracker, one class per milestone.

Run everything with ``python -m pytest`` or a single milestone with ``python -m pytest -k Milestone2``.
Every test works in its own temporary folder (``tmp_path``) and passes dates explicitly, so the
results never depend on your files or on today's date.
"""

import dataclasses
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from expense_tracker import (
    Expense,
    ExpenseError,
    add_expense,
    filter_expenses,
    format_expenses,
    format_summary,
    load_expenses,
    main,
    make_expense,
    normalise_category,
    parse_amount,
    parse_date,
    parse_month,
    save_expenses,
    summarise_by_category,
    summarise_by_month,
    total,
)


@pytest.fixture
def sample() -> list[Expense]:
    """Four expenses across two months and three categories (deliberately not in date order)."""
    return [
        make_expense("12.50", "groceries", "2026-10-01", "weekly shop"),
        make_expense("3.20", "transport", "2026-10-02", "bus"),
        make_expense("30.00", "Groceries", "2026-09-28", "big shop"),
        make_expense("15", "eating out", "2026-10-02"),
    ]


@pytest.fixture
def data_file(tmp_path: Path) -> Path:
    """Path of a data file that does not exist yet."""
    return tmp_path / "expenses.json"


class TestMilestone1Model:
    """Milestone 1: parse and validate the values that make up an expense."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("12.5", "12.50"), ("12", "12.00"), (" 7.25 ", "7.25"), ("0.01", "0.01"), ("1.230", "1.23")],
    )
    def test_parse_amount_accepts_positive_amounts(self, text: str, expected: str) -> None:
        amount = parse_amount(text)
        assert isinstance(amount, Decimal), "amounts must be Decimal, never float"
        assert str(amount) == expected, "amounts are rounded to exactly two decimal places"

    @pytest.mark.parametrize("text", ["abc", "", "0", "-5", "1.234", "NaN", "Infinity", "5000000"])
    def test_parse_amount_rejects_invalid_amounts(self, text: str) -> None:
        with pytest.raises(ExpenseError):
            parse_amount(text)

    def test_amounts_add_up_exactly(self) -> None:
        assert parse_amount("0.10") + parse_amount("0.20") == parse_amount("0.30")

    def test_parse_date_accepts_iso_dates(self) -> None:
        assert parse_date("2026-10-01") == date(2026, 10, 1)
        assert parse_date(" 2024-02-29 ") == date(2024, 2, 29)

    @pytest.mark.parametrize("text", ["01/10/2026", "2026-13-01", "2026-02-30", "20261001", "yesterday", ""])
    def test_parse_date_rejects_other_formats(self, text: str) -> None:
        with pytest.raises(ExpenseError, match="YYYY-MM-DD"):
            parse_date(text)

    @pytest.mark.parametrize("text", ["2026-10", " 2026-01 "])
    def test_parse_month_accepts_year_and_month(self, text: str) -> None:
        assert parse_month(text) == text.strip()

    @pytest.mark.parametrize("text", ["2026-13", "2026-1", "Oct 2026", "2026-10-01"])
    def test_parse_month_rejects_other_formats(self, text: str) -> None:
        with pytest.raises(ExpenseError):
            parse_month(text)

    @pytest.mark.parametrize(
        ("text", "expected"), [("Groceries", "groceries"), ("  Eating   Out ", "eating out")]
    )
    def test_normalise_category(self, text: str, expected: str) -> None:
        assert normalise_category(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "x" * 31])
    def test_normalise_category_rejects_empty_or_long(self, text: str) -> None:
        with pytest.raises(ExpenseError):
            normalise_category(text)

    def test_make_expense_validates_every_field(self) -> None:
        expense = make_expense("4", " Coffee ", "2026-10-03", "  flat   white ")
        assert expense == Expense(Decimal("4.00"), "coffee", date(2026, 10, 3), "flat white")
        assert expense.month == "2026-10"

    def test_expense_is_immutable(self) -> None:
        expense = make_expense("4", "coffee", "2026-10-03")
        with pytest.raises(dataclasses.FrozenInstanceError):
            expense.amount = Decimal("1.00")  # type: ignore[misc]

    def test_expense_round_trips_through_a_dict(self) -> None:
        expense = make_expense("12.50", "groceries", "2026-10-01", "weekly shop")
        data = expense.to_dict()
        assert data == {
            "amount": "12.50",
            "category": "groceries",
            "date": "2026-10-01",
            "description": "weekly shop",
        }
        assert Expense.from_dict(data) == expense

    @pytest.mark.parametrize(
        "data",
        [
            {"category": "food", "date": "2026-10-01"},
            ["12.50", "food", "2026-10-01"],
            {"amount": "-1", "category": "food", "date": "2026-10-01"},
        ],
    )
    def test_from_dict_rejects_bad_records(self, data: object) -> None:
        with pytest.raises(ExpenseError):
            Expense.from_dict(data)


class TestMilestone2Storage:
    """Milestone 2: load and save the JSON file safely."""

    def test_missing_file_means_no_expenses(self, data_file: Path) -> None:
        assert load_expenses(data_file) == []

    def test_save_then_load_round_trips(self, data_file: Path, sample: list[Expense]) -> None:
        save_expenses(data_file, sample)
        assert load_expenses(data_file) == sample

    def test_saved_file_is_versioned_json_with_string_amounts(
        self, data_file: Path, sample: list[Expense]
    ) -> None:
        save_expenses(data_file, sample)
        data = json.loads(data_file.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["expenses"][0] == {
            "amount": "12.50",
            "category": "groceries",
            "date": "2026-10-01",
            "description": "weekly shop",
        }

    def test_corrupt_json_gives_a_clear_error(self, data_file: Path) -> None:
        data_file.write_text('{"version": 1, "expenses": [', encoding="utf-8")
        with pytest.raises(ExpenseError, match="not valid JSON") as excinfo:
            load_expenses(data_file)
        assert "expenses.json" in str(excinfo.value), "the message should name the file"

    @pytest.mark.parametrize("content", ["[]", '{"version": 1}', '{"version": 1, "expenses": {}}'])
    def test_wrong_shape_is_rejected(self, data_file: Path, content: str) -> None:
        data_file.write_text(content, encoding="utf-8")
        with pytest.raises(ExpenseError):
            load_expenses(data_file)

    def test_invalid_record_reports_its_position(self, data_file: Path) -> None:
        good = {"amount": "1.00", "category": "food", "date": "2026-10-01", "description": ""}
        bad = {"amount": "lots", "category": "food", "date": "2026-10-01", "description": ""}
        data_file.write_text(json.dumps({"version": 1, "expenses": [good, bad]}), encoding="utf-8")
        with pytest.raises(ExpenseError, match="#2"):
            load_expenses(data_file)

    def test_failed_save_leaves_the_old_file_and_no_temp_files(
        self, data_file: Path, sample: list[Expense], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        save_expenses(data_file, sample[:1])
        before = data_file.read_text(encoding="utf-8")

        def broken_replace(src: object, dst: object) -> None:
            raise OSError("simulated crash while replacing the file")

        monkeypatch.setattr(os, "replace", broken_replace)
        with pytest.raises(OSError, match="simulated"):
            save_expenses(data_file, sample)
        assert data_file.read_text(encoding="utf-8") == before, (
            "write to a temporary file, then os.replace it"
        )
        assert [p.name for p in data_file.parent.iterdir()] == ["expenses.json"], (
            "clean up the temporary file"
        )

    def test_save_creates_missing_folders(self, tmp_path: Path, sample: list[Expense]) -> None:
        target = tmp_path / "data" / "2026" / "expenses.json"
        save_expenses(target, sample)
        assert load_expenses(target) == sample

    def test_add_expense_appends_and_counts(self, data_file: Path, sample: list[Expense]) -> None:
        assert add_expense(data_file, sample[0]) == 1
        assert add_expense(data_file, sample[1]) == 2
        assert load_expenses(data_file) == sample[:2]


class TestMilestone3Reports:
    """Milestone 3: filter, total and summarise expenses."""

    def test_filter_by_category_normalises_the_query(self, sample: list[Expense]) -> None:
        result = filter_expenses(sample, category="  GROCERIES ")
        assert [e.description for e in result] == ["big shop", "weekly shop"]

    def test_filter_by_month(self, sample: list[Expense]) -> None:
        assert [e.amount for e in filter_expenses(sample, month="2026-09")] == [Decimal("30.00")]

    def test_filter_sorts_by_date_and_keeps_order_of_ties(self, sample: list[Expense]) -> None:
        result = filter_expenses(sample)
        assert [e.spent_on.day for e in result] == [28, 1, 2, 2]
        assert [e.category for e in result][2:] == ["transport", "eating out"]

    def test_filter_by_category_and_month(self, sample: list[Expense]) -> None:
        assert filter_expenses(sample, category="groceries", month="2026-10") == [sample[0]]

    def test_filter_rejects_a_bad_month(self, sample: list[Expense]) -> None:
        with pytest.raises(ExpenseError):
            filter_expenses(sample, month="October")

    def test_total(self, sample: list[Expense]) -> None:
        assert total(sample) == Decimal("60.70")
        assert str(total([])) == "0.00"

    def test_summary_by_category_is_largest_first(self, sample: list[Expense]) -> None:
        assert list(summarise_by_category(sample).items()) == [
            ("groceries", Decimal("42.50")),
            ("eating out", Decimal("15.00")),
            ("transport", Decimal("3.20")),
        ]

    def test_summary_by_category_breaks_ties_alphabetically(self) -> None:
        tied = [make_expense("5", "tea", "2026-10-01"), make_expense("5", "cake", "2026-10-01")]
        assert list(summarise_by_category(tied)) == ["cake", "tea"]

    def test_summary_by_month_is_in_calendar_order(self, sample: list[Expense]) -> None:
        assert summarise_by_month(sample) == {"2026-09": Decimal("30.00"), "2026-10": Decimal("30.70")}
        assert list(summarise_by_month(sample)) == ["2026-09", "2026-10"]

    def test_format_expenses_shows_rows_and_total(self, sample: list[Expense]) -> None:
        text = format_expenses(filter_expenses(sample))
        lines = text.splitlines()
        assert "Date" in lines[0] and "Amount" in lines[0]
        assert lines[1].startswith("2026-09-28") and "30.00" in lines[1] and "big shop" in lines[1]
        assert lines[-1] == "4 expense(s), total 60.70"

    def test_format_expenses_when_empty(self) -> None:
        assert format_expenses([]) == "No expenses found."

    def test_format_summary_ends_with_total(self, sample: list[Expense]) -> None:
        lines = format_summary(summarise_by_category(sample), "Category").splitlines()
        assert lines[0].split() == ["Category", "Total"]
        assert lines[1].split() == ["groceries", "42.50"]
        assert lines[-1].split() == ["TOTAL", "60.70"]


class TestMilestone4Cli:
    """Milestone 4: the argparse command-line interface (called as main([...]), no subprocess)."""

    def run(self, data_file: Path, *args: str) -> int:
        return main(["--file", str(data_file), *args], today=date(2026, 10, 22))

    def test_add_then_list(self, data_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert (
            self.run(data_file, "add", "12.50", "Groceries", "--date", "2026-10-01", "-d", "weekly shop") == 0
        )
        assert "Added 12.50 to groceries on 2026-10-01" in capsys.readouterr().out
        assert self.run(data_file, "list") == 0
        out = capsys.readouterr().out
        assert "weekly shop" in out and "1 expense(s), total 12.50" in out

    def test_add_defaults_to_today(self, data_file: Path) -> None:
        assert self.run(data_file, "add", "3.20", "transport") == 0
        assert load_expenses(data_file)[0].spent_on == date(2026, 10, 22)

    @pytest.mark.parametrize("amount", ["-5", "abc", "0"])
    def test_add_rejects_bad_amounts(
        self, data_file: Path, capsys: pytest.CaptureFixture[str], amount: str
    ) -> None:
        assert self.run(data_file, "add", amount, "food", "--date", "2026-10-01") == 1
        err = capsys.readouterr().err
        assert err.startswith("error:") and "amount" in err
        assert not data_file.exists(), "nothing should be saved when validation fails"

    def test_list_filters(
        self, data_file: Path, sample: list[Expense], capsys: pytest.CaptureFixture[str]
    ) -> None:
        save_expenses(data_file, sample)
        assert self.run(data_file, "list", "--category", "groceries", "--month", "2026-10") == 0
        out = capsys.readouterr().out
        assert "weekly shop" in out and "big shop" not in out and "bus" not in out

    def test_list_with_no_data(self, data_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert self.run(data_file, "list") == 0
        assert "No expenses found." in capsys.readouterr().out

    def test_summary_by_category(
        self, data_file: Path, sample: list[Expense], capsys: pytest.CaptureFixture[str]
    ) -> None:
        save_expenses(data_file, sample)
        assert self.run(data_file, "summary") == 0
        lines = [line.split() for line in capsys.readouterr().out.splitlines()]
        assert ["groceries", "42.50"] in lines and ["TOTAL", "60.70"] in lines

    def test_summary_by_month(
        self, data_file: Path, sample: list[Expense], capsys: pytest.CaptureFixture[str]
    ) -> None:
        save_expenses(data_file, sample)
        assert self.run(data_file, "summary", "--by", "month") == 0
        lines = [line.split() for line in capsys.readouterr().out.splitlines()]
        assert lines[1:] == [["2026-09", "30.00"], ["2026-10", "30.70"], ["TOTAL", "60.70"]]

    def test_corrupt_file_is_reported_not_overwritten(
        self, data_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        data_file.write_text("this is not json", encoding="utf-8")
        assert self.run(data_file, "add", "1", "food", "--date", "2026-10-01") == 1
        assert "not valid JSON" in capsys.readouterr().err
        assert data_file.read_text(encoding="utf-8") == "this is not json"

    def test_default_file_is_in_the_current_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        assert main(["add", "2", "snacks", "--date", "2026-10-01"]) == 0
        assert (tmp_path / "expenses.json").exists()

    def test_unknown_command_is_a_usage_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["fly"])
        assert excinfo.value.code == 2
