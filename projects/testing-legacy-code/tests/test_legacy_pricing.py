"""Characterisation tests for legacy_pricing (milestones 1 and 2).

A characterisation test pins down what code DOES today, including its quirks, not what
it should do. These pass for both starter/ and solution/ because legacy_pricing.py is
identical in both. They are the reference answer for milestones 1 and 2: write your own
in tests/test_my_characterisation.py first (see the README), then compare.

The expected numbers were obtained by running the legacy code, not by hand: that is
the point of characterisation. Comments explain where each number comes from.
"""

from __future__ import annotations

import legacy_pricing
import pytest
from legacy_pricing import calc, calc_many

BOOK = {"sku": "BK-1", "price": 12.99, "qty": 1, "cat": "books"}
GADGET_45 = {"sku": "GD-2", "price": 45.0, "qty": 1, "cat": "gadgets"}


def book(price: float) -> dict:
    """A one-book cart: books have no VAT, so the item total equals the price."""
    return {"sku": "BK-X", "price": price, "qty": 1, "cat": "books"}


@pytest.fixture(autouse=True)
def fresh_orders(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """calc() appends to the global ORDERS list. Give each test its own empty list,
    so tests cannot affect each other (and the real list is restored afterwards)."""
    orders: list[dict] = []
    monkeypatch.setattr(legacy_pricing, "ORDERS", orders)
    return orders


class TestMilestone1Characterisation:
    """One plain assert per rule and per quirk, exactly as the legacy code behaves."""

    def test_one_book_with_standard_shipping(self) -> None:
        assert calc([BOOK], "regular") == 17.98  # 12.99 + 4.99 shipping below 50

    def test_returns_a_float_rounded_to_cents(self) -> None:
        result = calc([BOOK], "regular")
        assert isinstance(result, float)
        assert result == round(result, 2)

    def test_other_categories_pay_20_percent_vat(self) -> None:
        assert calc([GADGET_45], "regular") == 54.0  # 45 * 1.2; free shipping from 50

    def test_food_pays_5_percent_vat(self) -> None:
        food = {"sku": "FD-1", "price": 10.0, "qty": 1, "cat": "food"}
        assert calc([food], "regular", None, "express") == 23.0  # 10.5 + 12.5

    def test_missing_category_pays_20_percent_vat(self) -> None:
        item = {"sku": "GD-1", "price": 10.0, "qty": 1}
        assert calc([item], "regular", None, "express") == 24.5  # 12 + 12.5

    def test_bulk_discount_starts_at_10_items(self) -> None:
        nine = {"sku": "BK-2", "price": 10.0, "qty": 9, "cat": "books"}
        ten = {"sku": "BK-2", "price": 10.0, "qty": 10, "cat": "books"}
        assert calc([nine], "regular", None, "express") == 102.5  # 90 + 12.5
        assert calc([ten], "regular", None, "express") == 107.5  # 100 * 0.95 + 12.5

    def test_member_and_staff_discounts(self) -> None:
        assert calc([BOOK], "member") == 16.68  # 12.99 * 0.9 = 11.691, + 4.99
        assert calc([BOOK], "staff") == 14.08  # 12.99 * 0.7 = 9.093, + 4.99

    def test_save10_coupon(self) -> None:
        assert calc([BOOK], "regular", "SAVE10") == 16.68

    def test_flat5_coupon_only_strictly_above_50(self) -> None:
        assert calc([book(50.0)], "regular", "FLAT5") == 50.0  # not above 50: no discount
        assert calc([book(60.0)], "regular", "FLAT5") == 55.0

    def test_express_shipping_is_always_charged(self) -> None:
        assert calc([book(100.0)], "regular", None, "express") == 112.5

    def test_staff_discount_and_save10_stack(self) -> None:
        assert calc([book(100.0)], "staff", "SAVE10") == 63.0  # 100 * 0.7 * 0.9

    def test_every_order_is_recorded_in_a_global_list(self, fresh_orders: list[dict]) -> None:
        calc([BOOK], "regular")
        calc([BOOK], "member")
        assert fresh_orders == [{"cust": "regular", "total": 17.98}, {"cust": "member", "total": 16.68}]

    def test_calc_many_prices_each_order(self) -> None:
        orders = [([BOOK], "member", None, "std"), ([BOOK], "staff", "SAVE10", "express")]
        assert calc_many(orders) == [16.68, 20.68]

    # --- Quirks: surprising behaviour that callers may rely on. Pin it; decide later. ---

    def test_quirk_unknown_shipping_method_ships_for_free(self) -> None:
        assert calc([book(30.0)], "regular", None, "EXPRESS") == 30.0
        assert calc([book(30.0)], "regular", None, "std") == 34.99

    def test_quirk_unknown_coupon_is_silently_ignored(self) -> None:
        assert calc([book(30.0)], "regular", "save10") == 34.99

    def test_quirk_unknown_customer_type_pays_the_regular_price(self) -> None:
        assert calc([book(30.0)], "vip") == 34.99

    def test_quirk_negative_quantity_gives_a_negative_total(self) -> None:
        refund = {"sku": "BK-R", "price": 20.0, "qty": -3, "cat": "books"}
        assert calc([refund], "regular") == -55.01  # -60 + 4.99 shipping

    def test_quirk_empty_cart_still_costs_shipping(self) -> None:
        assert calc([], "regular") == 4.99

    def test_quirk_float_rounding_rounds_this_half_cent_down(self) -> None:
        sweets = {"sku": "SW-1", "price": 0.1, "qty": 3, "cat": "food"}
        # Exact arithmetic gives 0.3 * 1.05 + 12.5 = 12.815, but the float is slightly below.
        assert calc([sweets], "regular", None, "express") == 12.81

    def test_quirk_flat5_can_cost_the_customer_free_shipping(self) -> None:
        assert calc([GADGET_45], "regular") == 54.0
        assert calc([GADGET_45], "regular", "FLAT5") == 53.99  # 54 - 5 = 49 < 50, so + 4.99


class TestMilestone2FixtureStyle:
    """The same knowledge, table-driven: a cart factory fixture, parametrize with ids,
    and pytest.raises for the errors the legacy code raises today."""

    @pytest.fixture
    def make_cart(self):
        """Return a function that builds a legacy cart from (price, qty, category) tuples."""

        def make(*lines: tuple[float, int, str | None]) -> list[dict]:
            cart = []
            for number, (price, qty, category) in enumerate(lines, start=1):
                item: dict = {"sku": f"SKU-{number}", "price": price, "qty": qty}
                if category is not None:
                    item["cat"] = category
                cart.append(item)
            return cart

        return make

    @pytest.mark.parametrize(
        ("lines", "customer", "coupon", "shipping", "expected"),
        [
            pytest.param([(12.99, 1, "books")], "regular", None, "std", 17.98, id="book-regular"),
            pytest.param(
                [(12.99, 1, "books")], "member", "SAVE10", "express", 23.02, id="book-member-save10"
            ),
            pytest.param(
                [(12.99, 1, "books")], "staff", "FLAT5", "std", 14.08, id="book-staff-flat5-too-small"
            ),
            pytest.param(
                [(3.49, 12, "food"), (19.99, 2, None)], "regular", None, "std", 89.75, id="bulk-food"
            ),
            pytest.param(
                [(3.49, 12, "food"), (19.99, 2, None)], "member", "SAVE10", "std", 72.7, id="bulk-member"
            ),
            pytest.param(
                [(3.49, 12, "food"), (19.99, 2, None)], "staff", "FLAT5", "express", 70.33, id="bulk-staff"
            ),
            pytest.param([(45.0, 1, "gadgets")], "member", "SAVE10", "std", 48.73, id="gadget-under-50"),
            pytest.param([(45.0, 1, "gadgets")], "staff", None, "express", 50.3, id="gadget-staff-express"),
            pytest.param(
                [(7.5, 10, "books"), (0.99, 3, "food")], "regular", None, "std", 74.37, id="bulk-books"
            ),
            pytest.param(
                [(7.5, 10, "books"), (0.99, 3, "food")], "staff", "SAVE10", "std", 51.84, id="books-staff"
            ),
            pytest.param(
                [(7.5, 10, "books"), (0.99, 3, "food")], "staff", "FLAT5", "std", 52.05, id="books-flat5"
            ),
        ],
    )
    def test_golden_master(
        self, make_cart, lines: list[tuple], customer: str, coupon: str | None, shipping: str, expected: float
    ) -> None:
        assert calc(make_cart(*lines), customer, coupon, shipping) == expected

    @pytest.mark.parametrize(
        ("cart", "error"),
        [
            pytest.param([{"sku": "X", "qty": 1}], KeyError, id="missing-price"),
            pytest.param([{"sku": "X", "price": 1.0}], KeyError, id="missing-qty"),
            pytest.param(
                [{"sku": "X", "price": "9.99", "qty": 1, "cat": "books"}], TypeError, id="price-as-text"
            ),
            pytest.param(None, TypeError, id="no-cart"),
        ],
    )
    def test_errors_the_legacy_code_raises(self, cart: object, error: type[Exception]) -> None:
        with pytest.raises(error):
            calc(cart, "regular")

    def test_failed_orders_are_not_recorded(self, fresh_orders: list[dict]) -> None:
        with pytest.raises(KeyError):
            calc([{"sku": "X", "qty": 1}], "regular")
        assert fresh_orders == []
