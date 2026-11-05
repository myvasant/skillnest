"""Tests for the refactored pricing_engine (milestones 3 to 5).

Written in a fixture-based style: fixtures build inputs, ``pytest.mark.parametrize``
lists cases with readable ids, and ``pytest.raises(..., match=...)`` checks errors.
"""

from __future__ import annotations

import ast
import itertools
from decimal import Decimal
from pathlib import Path

import legacy_pricing
import pricing_engine
import pytest
from pricing_engine import (
    LineItem,
    PricingError,
    apply_bulk_discount,
    apply_coupon,
    apply_customer_discount,
    line_total,
    order_total,
    price_cart,
    shipping_cost,
    tax_rate,
    to_decimal,
    to_money,
)

D = Decimal

CARTS = {
    "one-book": [{"sku": "BK-1", "price": 12.99, "qty": 1, "cat": "books"}],
    "bulk-food-and-gadget": [
        {"sku": "FD-1", "price": 3.49, "qty": 12, "cat": "food"},
        {"sku": "GD-1", "price": 19.99, "qty": 2},
    ],
    "gadget-near-50": [{"sku": "GD-2", "price": 45.0, "qty": 1, "cat": "gadgets"}],
    "bulk-books-and-snacks": [
        {"sku": "BK-2", "price": 7.5, "qty": 10, "cat": "books"},
        {"sku": "FD-2", "price": 0.99, "qty": 3, "cat": "food"},
    ],
}
GRID = list(
    itertools.product(CARTS, ["regular", "member", "staff"], [None, "SAVE10", "FLAT5"], ["std", "express"])
)


@pytest.fixture
def book() -> LineItem:
    return LineItem("BK-1", D("12.99"), 1, "books")


@pytest.fixture
def legacy_orders(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """An empty, private ORDERS list for legacy_pricing (restored after the test)."""
    orders: list[dict] = []
    monkeypatch.setattr(legacy_pricing, "ORDERS", orders)
    return orders


def single_book_total(price: str, quantity: int = 1, **options: str) -> Decimal:
    """Total for one line of books (0% VAT, so the line total is price x quantity)."""
    return order_total([LineItem("BK-X", D(price), quantity, "books")], **options)


class TestMilestone3PureFunctions:
    """Each business rule as a small pure function with Decimal money."""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [("2.675", "2.68"), ("2.665", "2.67"), ("2.664", "2.66"), ("-1.005", "-1.01"), ("10", "10.00")],
    )
    def test_to_money_rounds_half_up_to_cents(self, amount: str, expected: str) -> None:
        result = to_money(D(amount))
        assert result == D(expected)
        assert str(result) == expected, "always two decimal places"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0.1, D("0.1")), ("9.99", D("9.99")), (" 3.50 ", D("3.50")), (3, D(3)), (D("1.5"), D("1.5"))],
        ids=["float", "text", "text-with-spaces", "int", "decimal"],
    )
    def test_to_decimal(self, value: object, expected: Decimal) -> None:
        assert to_decimal(value) == expected

    @pytest.mark.parametrize("value", [True, None, "abc", "nan", float("inf"), [1]])
    def test_to_decimal_rejects_non_numbers(self, value: object) -> None:
        with pytest.raises(PricingError, match="number"):
            to_decimal(value, "price")

    def test_line_item_is_valid_and_immutable(self, book: LineItem) -> None:
        assert (book.sku, book.price, book.quantity, book.category) == ("BK-1", D("12.99"), 1, "books")
        assert LineItem("X", D("1"), 2).category == "other"
        with pytest.raises(AttributeError):
            book.quantity = 5  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("price", "quantity", "message"),
        [
            pytest.param(D("-0.01"), 1, "price", id="negative-price"),
            pytest.param(9.99, 1, "price", id="float-price"),
            pytest.param(D("NaN"), 1, "price", id="nan-price"),
            pytest.param(D("1"), 0, "quantity", id="zero-quantity"),
            pytest.param(D("1"), -3, "quantity", id="negative-quantity"),
            pytest.param(D("1"), 1.5, "quantity", id="fractional-quantity"),
            pytest.param(D("1"), True, "quantity", id="bool-quantity"),
        ],
    )
    def test_line_item_rejects_invalid_values(self, price: object, quantity: object, message: str) -> None:
        with pytest.raises(PricingError, match=message):
            LineItem("X", price, quantity)  # type: ignore[arg-type]

    def test_line_item_from_legacy_dict(self) -> None:
        assert LineItem.from_dict({"sku": "BK-1", "price": 12.99, "qty": 1, "cat": "books"}) == LineItem(
            "BK-1", D("12.99"), 1, "books"
        )
        assert LineItem.from_dict({"sku": "S", "price": 0.1, "qty": 3}).price == D("0.1")
        assert LineItem.from_dict({"sku": "S", "price": 1, "qty": 3}).category == "other"
        with pytest.raises(PricingError, match="price"):
            LineItem.from_dict({"sku": "S", "qty": 3})

    @pytest.mark.parametrize(
        ("category", "rate"),
        [("books", "0"), ("food", "0.05"), ("gadgets", "0.20"), ("other", "0.20"), ("", "0.20")],
    )
    def test_tax_rate(self, category: str, rate: str) -> None:
        assert tax_rate(category) == D(rate)

    @pytest.mark.parametrize(("quantity", "expected"), [(1, "100"), (9, "100"), (10, "95"), (25, "95")])
    def test_bulk_discount(self, quantity: int, expected: str) -> None:
        assert apply_bulk_discount(D("100"), quantity) == D(expected)

    @pytest.mark.parametrize(
        ("item", "expected"),
        [
            pytest.param(LineItem("F", D("10"), 10, "food"), "99.75", id="bulk-food"),
            pytest.param(LineItem("B", D("12.99"), 1, "books"), "12.99", id="book"),
            pytest.param(LineItem("G", D("45"), 1, "gadgets"), "54", id="gadget"),
        ],
    )
    def test_line_total(self, item: LineItem, expected: str) -> None:
        assert line_total(item) == D(expected)

    @pytest.mark.parametrize(
        ("customer", "expected"), [("regular", "100"), ("member", "90"), ("staff", "70")]
    )
    def test_customer_discount(self, customer: str, expected: str) -> None:
        assert apply_customer_discount(D("100"), customer) == D(expected)

    @pytest.mark.parametrize("customer", ["vip", "Member", ""])
    def test_unknown_customer_type_is_an_error(self, customer: str) -> None:
        with pytest.raises(PricingError, match="customer"):
            apply_customer_discount(D("100"), customer)

    @pytest.mark.parametrize(
        ("amount", "code", "expected"),
        [
            ("60", None, "60"),
            ("60", "SAVE10", "54"),
            ("60", "FLAT5", "55"),
            ("50", "FLAT5", "50"),
            ("50.01", "FLAT5", "45.01"),
        ],
    )
    def test_coupons(self, amount: str, code: str | None, expected: str) -> None:
        assert apply_coupon(D(amount), code) == D(expected)

    @pytest.mark.parametrize("code", ["save10", "FREESHIP", ""])
    def test_unknown_coupon_is_an_error(self, code: str) -> None:
        with pytest.raises(PricingError, match="coupon"):
            apply_coupon(D("60"), code)

    @pytest.mark.parametrize(
        ("amount", "method", "expected"),
        [
            ("49.99", "std", "4.99"),
            ("50", "std", "0"),
            ("0", "express", "12.50"),
            ("100", "express", "12.50"),
        ],
    )
    def test_shipping_cost(self, amount: str, method: str, expected: str) -> None:
        assert shipping_cost(D(amount), method) == D(expected)

    @pytest.mark.parametrize("method", ["EXPRESS", "next-day", ""])
    def test_unknown_shipping_method_is_an_error(self, method: str) -> None:
        with pytest.raises(PricingError, match="shipping"):
            shipping_cost(D("10"), method)

    def test_no_global_mutable_state(self) -> None:
        mutable = {
            name: type(value).__name__
            for name, value in vars(pricing_engine).items()
            if not name.startswith("__") and isinstance(value, list | dict | set)
        }
        assert mutable == {}, "use tuples, frozensets or types.MappingProxyType for module-level tables"

    def test_does_not_import_the_legacy_module(self) -> None:
        tree = ast.parse(Path(pricing_engine.__file__ or "").read_text(encoding="utf-8"))
        imported = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert "legacy_pricing" not in imported


class TestMilestone4Equivalence:
    """The refactor must give the same totals as the legacy code for every valid order,
    and differ only where we decided to change the behaviour."""

    @pytest.mark.parametrize(
        ("cart_name", "customer", "coupon", "shipping"), GRID, ids=lambda value: str(value)
    )
    def test_matches_legacy_on_valid_orders(
        self, legacy_orders: list[dict], cart_name: str, customer: str, coupon: str | None, shipping: str
    ) -> None:
        cart = CARTS[cart_name]
        expected = Decimal(str(legacy_pricing.calc(cart, customer, coupon, shipping)))
        assert price_cart(cart, customer, coupon, shipping) == expected

    def test_returns_decimal_with_two_places(self) -> None:
        total = price_cart(CARTS["gadget-near-50"])
        assert isinstance(total, Decimal)
        assert str(total) == "54.00"

    def test_order_total_and_price_cart_agree(self, book: LineItem) -> None:
        assert order_total([book], customer="member", coupon="SAVE10", shipping="express") == price_cart(
            CARTS["one-book"], "member", "SAVE10", "express"
        )

    def test_deliberate_change_half_up_rounding(self, legacy_orders: list[dict]) -> None:
        sweets = [{"sku": "SW-1", "price": 0.1, "qty": 3, "cat": "food"}]  # exact total 12.815
        assert legacy_pricing.calc(sweets, "regular", None, "express") == 12.81
        assert price_cart(sweets, "regular", None, "express") == D("12.82")

    @pytest.mark.parametrize(
        ("cart", "options", "message"),
        [
            pytest.param(CARTS["one-book"], {"shipping": "EXPRESS"}, "shipping", id="unknown-shipping"),
            pytest.param(CARTS["one-book"], {"coupon": "save10"}, "coupon", id="unknown-coupon"),
            pytest.param(CARTS["one-book"], {"customer": "vip"}, "customer", id="unknown-customer"),
            pytest.param([{"sku": "R", "price": 20.0, "qty": -3}], {}, "quantity", id="negative-quantity"),
            pytest.param([{"sku": "R", "price": 20.0, "qty": 0}], {}, "quantity", id="zero-quantity"),
            pytest.param([{"sku": "R", "price": -20.0, "qty": 1}], {}, "price", id="negative-price"),
            pytest.param([{"sku": "R", "qty": 1}], {}, "missing 'price'", id="missing-price"),
            pytest.param(["not a dict"], {}, "dictionary", id="not-a-dict"),
            pytest.param([], {}, "at least one item", id="empty-cart"),
        ],
    )
    def test_deliberate_change_invalid_orders_raise(self, cart: list, options: dict, message: str) -> None:
        with pytest.raises(PricingError, match=message):
            price_cart(cart, **options)

    def test_errors_name_the_cart_line(self) -> None:
        cart = [CARTS["one-book"][0], {"sku": "BAD", "price": 1.0, "qty": 0}]
        with pytest.raises(PricingError, match=r"cart item #2"):
            price_cart(cart)

    def test_numeric_text_prices_are_now_accepted(self) -> None:
        assert price_cart([{"sku": "T", "price": "9.99", "qty": 1, "cat": "books"}]) == D("14.98")

    def test_deliberate_change_no_global_order_log(self, legacy_orders: list[dict]) -> None:
        first = price_cart(CARTS["one-book"])
        second = price_cart(CARTS["one-book"])
        assert first == second == D("17.98")
        assert legacy_orders == [], "the refactored code must not write to legacy_pricing.ORDERS"


class TestMilestone5Boundaries:
    """Boundary tests. Each pair would fail if a comparison were off by one, for example
    if someone 'simplified' > into >= (a mutation that a weaker suite would not notice)."""

    @pytest.mark.parametrize(
        ("price", "quantity", "options", "expected"),
        [
            pytest.param("10", 9, {"shipping": "express"}, "102.50", id="bulk-9-items-no-discount"),
            pytest.param("10", 10, {"shipping": "express"}, "107.50", id="bulk-10-items-discount"),
            pytest.param("50.00", 1, {"coupon": "FLAT5"}, "50.00", id="flat5-at-exactly-50"),
            pytest.param("50.01", 1, {"coupon": "FLAT5"}, "50.00", id="flat5-above-50-then-shipping"),
            pytest.param("49.99", 1, {}, "54.98", id="std-shipping-below-50"),
            pytest.param("50.00", 1, {}, "50.00", id="std-shipping-free-at-50"),
            pytest.param(
                "100", 1, {"customer": "staff", "coupon": "SAVE10"}, "63.00", id="staff-and-save10-stack"
            ),
            pytest.param("60", 1, {"customer": "member", "coupon": "FLAT5"}, "53.99", id="member-then-flat5"),
            pytest.param("0", 1, {}, "4.99", id="free-item-still-ships"),
        ],
    )
    def test_boundaries(
        self, legacy_orders: list[dict], price: str, quantity: int, options: dict, expected: str
    ) -> None:
        assert single_book_total(price, quantity, **options) == D(expected)
        # The legacy code agrees on every boundary: these rules were not meant to change.
        legacy = legacy_pricing.calc(
            [{"sku": "BK-X", "price": float(price), "qty": quantity, "cat": "books"}],
            options.get("customer", "regular"),
            options.get("coupon"),
            options.get("shipping", "std"),
        )
        assert Decimal(str(legacy)) == D(expected)
