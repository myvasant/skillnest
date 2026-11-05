"""Behaviour tests for the CSV processor, one class per milestone.

Run everything with ``python -m pytest`` or a single milestone with ``python -m pytest -k Milestone3``.
Files are written to pytest's ``tmp_path``; most tests feed CSV text through ``io.StringIO``.
"""

import csv
import io
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from csv_processor import (
    CsvProcessingError,
    GroupStats,
    Rejected,
    RowError,
    Sale,
    aggregate,
    build_report,
    clean_row,
    clean_rows,
    clean_text,
    escape_formula,
    format_report,
    is_missing,
    main,
    parse_iso_date,
    parse_money,
    parse_whole_number,
    read_rows,
    write_summary_csv,
)

HEADER = "order_id,order_date,region,product,quantity,unit_price\n"

# Line numbers (the header is line 1) are used in the expectations below.
SAMPLE = HEADER + (
    "A001,2026-03-01,North,Notebook,3,4.50\n"  # 2  ok
    "A002,2026-03-01, south ,Pen,10,1.20\n"  # 3  ok (region needs cleaning)
    "A003,2026-03-02,North,Stapler,1,12.00\n"  # 4  ok
    "A004,2026-03-05,,Notebook,2,4.50\n"  # 5  ok (missing region -> Unknown)
    "A005,2026-03-07,South,Pen,ten,1.20\n"  # 6  bad quantity
    "A006,2026-02-30,North,Pen,1,1.20\n"  # 7  impossible date
    "A007,2026-04-02,East,Notebook,NA,4.50\n"  # 8  missing quantity
    "A003,2026-04-03,North,Stapler,1,12.00\n"  # 9  duplicate order id
    "A008,2026-04-04,east,Stapler,2,$11.50\n"  # 10 ok (currency symbol)
    "A009,2026-04-05,West,Desk lamp,1,1,200.00\n"  # 11 unquoted comma -> too many fields
)

VALID_ROW = {
    "order_id": "A001",
    "order_date": "2026-03-01",
    "region": "North",
    "product": "Notebook",
    "quantity": "3",
    "unit_price": "4.50",
}


def make_sale(order_id: str, day: str, region: str, product: str, quantity: int, price: str) -> Sale:
    return Sale(order_id, date.fromisoformat(day), region, product, quantity, Decimal(price))


@pytest.fixture
def sales() -> list[Sale]:
    """The five valid sales from SAMPLE, built directly so Milestone 4 does not depend on 2-3."""
    return [
        make_sale("A001", "2026-03-01", "North", "Notebook", 3, "4.50"),
        make_sale("A002", "2026-03-01", "South", "Pen", 10, "1.20"),
        make_sale("A003", "2026-03-02", "North", "Stapler", 1, "12.00"),
        make_sale("A004", "2026-03-05", "Unknown", "Notebook", 2, "4.50"),
        make_sale("A008", "2026-04-04", "East", "Stapler", 2, "11.50"),
    ]


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "sales.csv"
    path.write_text(SAMPLE, encoding="utf-8", newline="")
    return path


class TestMilestone1Values:
    """Milestone 1: recognise missing values and parse numbers, prices and dates."""

    @pytest.mark.parametrize("value", [None, "", "   ", "NA", "n/a", "N/A", "NaN", "null", "None", " - "])
    def test_missing_markers(self, value: str | None) -> None:
        assert is_missing(value) is True

    @pytest.mark.parametrize("value", ["0", "North", "none of these", " x "])
    def test_real_values_are_not_missing(self, value: str) -> None:
        assert is_missing(value) is False

    def test_clean_text_collapses_whitespace(self) -> None:
        assert clean_text("  Desk   lamp \t") == "Desk lamp"

    @pytest.mark.parametrize(("text", "expected"), [("3", 3), (" 12 ", 12), ("4.0", 4), ("0", 0)])
    def test_parse_whole_number(self, text: str, expected: int) -> None:
        result = parse_whole_number(text)
        assert result == expected and isinstance(result, int)

    @pytest.mark.parametrize("text", ["ten", "2.5", "", "inf"])
    def test_parse_whole_number_rejects_non_integers(self, text: str) -> None:
        with pytest.raises(ValueError, match="whole number"):
            parse_whole_number(text)

    def test_parse_whole_number_enforces_minimum(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            parse_whole_number("0", minimum=1)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("4.5", "4.50"),
            ("12", "12.00"),
            ("$11.50", "11.50"),
            ("£3", "3.00"),
            (" € 2.25 ", "2.25"),
            ("0", "0.00"),
        ],
    )
    def test_parse_money(self, text: str, expected: str) -> None:
        result = parse_money(text)
        assert isinstance(result, Decimal), "prices must be Decimal, never float"
        assert str(result) == expected

    @pytest.mark.parametrize("text", ["abc", "-1.00", "1,200.00", "4.999", "NaN", "", "$"])
    def test_parse_money_rejects_bad_prices(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_money(text)

    def test_parse_iso_date(self) -> None:
        assert parse_iso_date(" 2026-03-01 ") == date(2026, 3, 1)

    @pytest.mark.parametrize("text", ["2026-02-30", "01/03/2026", "20260301", "March 1", ""])
    def test_parse_iso_date_rejects_other_layouts(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_iso_date(text)


class TestMilestone2Rows:
    """Milestone 2: turn one raw row (a dict of strings) into a typed Sale or a RowError."""

    def test_valid_row_becomes_a_typed_sale(self) -> None:
        sale = clean_row(VALID_ROW)
        assert sale == Sale("A001", date(2026, 3, 1), "North", "Notebook", 3, Decimal("4.50"))
        assert sale.revenue == Decimal("13.50")
        assert sale.month == "2026-03"

    def test_text_is_normalised(self) -> None:
        row = {**VALID_ROW, "order_id": " A001 ", "region": " south  east ", "product": "  Desk   lamp "}
        sale = clean_row(row)
        assert (sale.order_id, sale.region, sale.product) == ("A001", "South East", "Desk lamp")

    @pytest.mark.parametrize("region", ["", "NA", None])
    def test_missing_region_defaults_to_unknown(self, region: str | None) -> None:
        assert clean_row({**VALID_ROW, "region": region}).region == "Unknown"

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("order_id", ""),
            ("order_date", "2026-02-30"),
            ("order_date", "n/a"),
            ("product", "null"),
            ("quantity", "ten"),
            ("quantity", "0"),
            ("quantity", "2.5"),
            ("unit_price", "abc"),
            ("unit_price", "-1"),
            ("unit_price", None),
        ],
    )
    def test_bad_values_name_their_column(self, column: str, value: str | None) -> None:
        with pytest.raises(RowError) as excinfo:
            clean_row({**VALID_ROW, column: value})
        assert excinfo.value.column == column

    def test_error_message_quotes_the_bad_value(self) -> None:
        with pytest.raises(RowError, match="'ten'"):
            clean_row({**VALID_ROW, "quantity": "ten"})

    def test_row_error_is_a_value_error(self) -> None:
        assert issubclass(RowError, ValueError)


class TestMilestone3Streaming:
    """Milestone 3: read the CSV lazily with csv.DictReader and clean every row."""

    def test_read_rows_yields_line_numbers_and_raw_rows(self) -> None:
        rows = list(read_rows(io.StringIO(SAMPLE)))
        assert len(rows) == 10
        assert rows[0] == (2, VALID_ROW)
        assert rows[1][0] == 3 and rows[1][1]["region"] == " south "

    def test_header_names_are_normalised(self) -> None:
        text = (
            " Order_ID ,ORDER_DATE,Region,Product,Quantity,Unit_Price\n"
            + "A001,2026-03-01,North,Notebook,3,4.50\n"
        )
        [(_, row)] = list(read_rows(io.StringIO(text)))
        assert row["order_id"] == "A001" and row["unit_price"] == "4.50"

    def test_missing_columns_are_reported(self) -> None:
        with pytest.raises(CsvProcessingError, match="quantity, unit_price"):
            list(read_rows(io.StringIO("order_id,order_date,region,product\nA1,2026-03-01,North,Pen\n")))

    def test_empty_input_is_reported(self) -> None:
        with pytest.raises(CsvProcessingError, match="empty"):
            list(read_rows(io.StringIO("")))

    def test_read_rows_is_lazy(self) -> None:
        def lines() -> Iterator[str]:
            yield HEADER
            yield "A001,2026-03-01,North,Notebook,3,4.50\n"
            raise AssertionError("read_rows read more lines than it needed: it should stream")

        rows = read_rows(lines())
        assert next(rows)[1]["order_id"] == "A001"

    def test_blank_lines_are_skipped_but_counted(self) -> None:
        text = HEADER + "A001,2026-03-01,North,Notebook,3,4.50\n\nA002,2026-03-01,North,Pen,1,1.20\n"
        assert [line for line, _ in read_rows(io.StringIO(text))] == [2, 4]

    def test_quoted_commas_stay_in_one_field(self) -> None:
        text = HEADER + 'A010,2026-05-01,North,"Pen, blue",2,1.50\n'
        [(_, row)] = list(read_rows(io.StringIO(text)))
        assert clean_row(row).product == "Pen, blue"

    def test_clean_rows_keeps_good_rows_and_rejects_bad_ones(self) -> None:
        results = list(clean_rows(read_rows(io.StringIO(SAMPLE))))
        kept = [item.order_id for item in results if isinstance(item, Sale)]
        rejected = [(item.line, item.column) for item in results if isinstance(item, Rejected)]
        assert kept == ["A001", "A002", "A003", "A004", "A008"]
        assert rejected == [(6, "quantity"), (7, "order_date"), (8, "quantity"), (9, "order_id"), (11, "row")]

    def test_duplicates_point_to_the_first_occurrence(self) -> None:
        results = list(clean_rows(read_rows(io.StringIO(SAMPLE))))
        duplicate = next(item for item in results if isinstance(item, Rejected) and item.column == "order_id")
        assert "line 4" in duplicate.reason
        assert duplicate.describe().startswith("line 9: order_id: ")

    def test_clean_rows_is_a_generator(self) -> None:
        assert isinstance(clean_rows(iter([])), Iterator)


class TestMilestone4Aggregation:
    """Milestone 4: group sales and compute count / total / mean / min / max in one pass."""

    def test_group_stats_accumulates(self) -> None:
        stats = GroupStats()
        for value in ("13.50", "12.00", "1.25"):
            stats.add(Decimal(value))
        assert (stats.count, stats.total, stats.minimum, stats.maximum) == (
            3,
            Decimal("26.75"),
            Decimal("1.25"),
            Decimal("13.50"),
        )
        assert stats.mean == Decimal("8.92")

    def test_empty_group_has_no_mean(self) -> None:
        with pytest.raises(ValueError):
            _ = GroupStats().mean

    def test_revenue_by_region(self, sales: list[Sale]) -> None:
        groups = aggregate(sales, by="region")
        assert list(groups) == ["East", "North", "South", "Unknown"]
        north = groups["North"]
        assert (north.count, north.total, north.mean, north.minimum, north.maximum) == (
            2,
            Decimal("25.50"),
            Decimal("12.75"),
            Decimal("12.00"),
            Decimal("13.50"),
        )

    def test_revenue_by_month_rounds_the_mean_half_up(self, sales: list[Sale]) -> None:
        groups = aggregate(sales, by="month")
        assert list(groups) == ["2026-03", "2026-04"]
        assert groups["2026-03"].total == Decimal("46.50")
        assert groups["2026-03"].mean == Decimal("11.63")  # 46.50 / 4 = 11.625

    def test_quantity_by_product(self, sales: list[Sale]) -> None:
        groups = aggregate(sales, by="product", value="quantity")
        assert {name: stats.total for name, stats in groups.items()} == {
            "Notebook": 5,
            "Pen": 10,
            "Stapler": 3,
        }

    def test_aggregate_accepts_a_one_shot_generator(self, sales: list[Sale]) -> None:
        groups = aggregate((sale for sale in sales), by="region")
        assert sum(stats.count for stats in groups.values()) == 5

    @pytest.mark.parametrize(("by", "value"), [("colour", "revenue"), ("region", "profit")])
    def test_aggregate_rejects_unknown_choices(self, sales: list[Sale], by: str, value: str) -> None:
        with pytest.raises(ValueError):
            aggregate(sales, by=by, value=value)

    def test_build_report_counts_rows(self) -> None:
        report = build_report(read_rows(io.StringIO(SAMPLE)))
        assert (report.rows_read, report.rows_kept, report.rows_rejected) == (10, 5, 5)
        assert dict(report.rejected_by_column) == {"quantity": 2, "order_date": 1, "order_id": 1, "row": 1}
        assert report.groups["North"].total == Decimal("25.50")

    def test_build_report_keeps_only_a_few_examples(self) -> None:
        report = build_report(read_rows(io.StringIO(SAMPLE)), max_examples=2)
        assert [item.line for item in report.examples] == [6, 7]
        assert report.rows_rejected == 5, "every rejection is still counted"

    def test_build_report_streams_many_rows(self) -> None:
        def lines() -> Iterator[str]:
            yield HEADER
            for number in range(5000):
                yield f"B{number},2026-01-{number % 28 + 1:02d},R{number % 3},Pen,1,0.10\n"

        report = build_report(read_rows(lines()), group_by="region")
        assert report.rows_kept == 5000
        assert report.groups["R0"].total == Decimal("166.70")


class TestMilestone5ReportCli:
    """Milestone 5: the text report, a formula-safe summary CSV and the argparse CLI."""

    def test_format_report(self) -> None:
        text = format_report(build_report(read_rows(io.StringIO(SAMPLE))))
        lines = text.splitlines()
        assert lines[0] == "Rows read: 10 | kept: 5 | rejected: 5"
        assert "  line 6: quantity: 'ten' is not a whole number" in lines
        assert "Revenue by region" in lines
        table = [line.split() for line in lines]
        assert ["North", "2", "25.50", "12.75", "12.00", "13.50"] in table
        assert ["TOTAL", "5", "69.50", "13.90", "9.00", "23.00"] in table

    def test_write_summary_csv(self) -> None:
        buffer = io.StringIO(newline="")
        write_summary_csv(build_report(read_rows(io.StringIO(SAMPLE))), buffer)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        assert rows[0] == ["region", "count", "total", "mean", "min", "max"]
        assert rows[2] == ["North", "2", "25.50", "12.75", "12.00", "13.50"]
        assert len(rows) == 5, "one header row plus one row per group (no TOTAL row)"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("=1+2", "'=1+2"),
            ("+44 20", "'+44 20"),
            ("-5", "'-5"),
            ("@SUM(A1)", "'@SUM(A1)"),
            ("North", "North"),
        ],
    )
    def test_escape_formula(self, text: str, expected: str) -> None:
        assert escape_formula(text) == expected

    def test_summary_csv_neutralises_formulas_from_the_input(self) -> None:
        text = HEADER + "A1,2026-03-01,=1+2,Pen,1,1.00\n"
        buffer = io.StringIO(newline="")
        write_summary_csv(build_report(read_rows(io.StringIO(text))), buffer)
        assert list(csv.reader(io.StringIO(buffer.getvalue())))[1][0] == "'=1+2"

    def test_main_prints_the_report(self, sample_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(sample_file)]) == 0
        out = capsys.readouterr().out
        assert "Rows read: 10 | kept: 5 | rejected: 5" in out and "Revenue by region" in out

    def test_main_writes_a_summary_csv(self, sample_file: Path, tmp_path: Path) -> None:
        target = tmp_path / "summary.csv"
        assert (
            main(
                [
                    str(sample_file),
                    "--group-by",
                    "product",
                    "--value",
                    "quantity",
                    "--summary-csv",
                    str(target),
                ]
            )
            == 0
        )
        with target.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert [row[0] for row in rows] == ["product", "Notebook", "Pen", "Stapler"]

    def test_main_handles_an_excel_byte_order_mark(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "excel.csv"
        path.write_text(SAMPLE, encoding="utf-8-sig", newline="")
        assert main([str(path)]) == 0
        assert "kept: 5" in capsys.readouterr().out

    def test_main_limits_examples(self, sample_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(sample_file), "--max-examples", "1"]) == 0
        out = capsys.readouterr().out
        assert "line 6:" in out and "line 7:" not in out

    def test_missing_file_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(tmp_path / "nope.csv")]) == 1
        assert "does not exist" in capsys.readouterr().err

    def test_missing_column_is_an_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "bad.csv"
        path.write_text("order_id,order_date,region,product,quantity\n", encoding="utf-8")
        assert main([str(path)]) == 1
        assert "unit_price" in capsys.readouterr().err

    def test_unknown_group_is_a_usage_error(self, sample_file: Path) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([str(sample_file), "--group-by", "colour"])
        assert excinfo.value.code == 2
