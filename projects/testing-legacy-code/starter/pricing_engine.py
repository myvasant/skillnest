"""Order pricing, refactored from ``legacy_pricing.calc``.  (STARTER)

Rebuild the legacy rules as small pure functions with named constants, Decimal money
and explicit errors. Keep every result identical to the legacy code for valid orders,
except for these deliberate changes (milestone 4 tests pin each one):

1. Totals are rounded half-up to the cent (legacy float round() turned 12.815 into 12.81).
2. Unknown customer types, coupon codes and shipping methods raise PricingError
   (legacy silently ignored them: "EXPRESS" meant free shipping).
3. Quantities must be whole numbers >= 1 and prices >= 0 (legacy allowed negative totals).
4. An empty order raises PricingError (legacy charged 4.99 shipping for nothing).
5. No global state: do not append to a module-level list; make rate tables read-only
   (types.MappingProxyType) or use constants.

TODO (milestone 3): replace every magic number from legacy_pricing.py with a named
constant here, for example BULK_MIN_QUANTITY = 10, BULK_DISCOUNT = Decimal("0.05"),
STANDARD_TAX_RATE = Decimal("0.20"), FREE_SHIPPING_MINIMUM = Decimal("50") ...
Never write Decimal(0.05): build Decimals from strings.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")
DEFAULT_CATEGORY = "other"


class PricingError(ValueError):
    """The order cannot be priced; the message says why."""


def to_decimal(value: Any, field: str = "value") -> Decimal:
    """Convert an int, numeric string, float or Decimal to a finite Decimal.

    * floats go through str() first: to_decimal(0.1) == Decimal("0.1");
    * bool, None, lists, non-numeric text ("abc"), NaN and infinity raise
      PricingError whose message contains "number".
    """
    # TODO (milestone 3)
    raise NotImplementedError("to_decimal")


def to_money(amount: Decimal) -> Decimal:
    """Round to whole cents, halves away from zero: 2.675 -> 2.68, 2.665 -> 2.67.

    Hint: amount.quantize(CENT, rounding=ROUND_HALF_UP).
    """
    # TODO (milestone 3)
    raise NotImplementedError("to_money")


@dataclass(frozen=True)
class LineItem:
    """One cart line. ``price`` is the unit price before tax."""

    sku: str
    price: Decimal
    quantity: int
    category: str = DEFAULT_CATEGORY

    def __post_init__(self) -> None:
        # TODO (milestone 3): raise PricingError mentioning "price" unless price is a
        # finite Decimal >= 0, and mentioning "quantity" unless quantity is an int >= 1
        # (bool is an int subclass in Python: reject True/False explicitly).
        pass

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LineItem:
        """Build an item from a legacy cart entry {"sku", "price", "qty", "cat"?}.

        Missing "sku", "price" or "qty" -> PricingError "cart item is missing 'price'";
        convert the price with to_decimal; a missing or empty "cat" means DEFAULT_CATEGORY.
        """
        # TODO (milestone 3)
        raise NotImplementedError("LineItem.from_dict")


def tax_rate(category: str) -> Decimal:
    """VAT rate for a category: books 0, food 0.05, anything else 0.20."""
    # TODO (milestone 3)
    raise NotImplementedError("tax_rate")


def apply_bulk_discount(amount: Decimal, quantity: int) -> Decimal:
    """Take 5% off a line of 10 or more items."""
    # TODO (milestone 3)
    raise NotImplementedError("apply_bulk_discount")


def line_total(item: LineItem) -> Decimal:
    """Price x quantity, then the bulk discount, then VAT. Do not round here."""
    # TODO (milestone 3)
    raise NotImplementedError("line_total")


def apply_customer_discount(amount: Decimal, customer: str) -> Decimal:
    """regular: 0%, member: 10%, staff: 30%; anything else -> PricingError ("customer")."""
    # TODO (milestone 3)
    raise NotImplementedError("apply_customer_discount")


def apply_coupon(amount: Decimal, code: str | None) -> Decimal:
    """None: unchanged; "SAVE10": 10% off; "FLAT5": 5 off only if amount > 50;
    any other code (including "save10") -> PricingError ("coupon")."""
    # TODO (milestone 3)
    raise NotImplementedError("apply_coupon")


def shipping_cost(amount: Decimal, method: str) -> Decimal:
    """ "std": 4.99, free from 50; "express": 12.50 always; other -> PricingError ("shipping")."""
    # TODO (milestone 3)
    raise NotImplementedError("shipping_cost")


def order_total(
    items: Iterable[LineItem],
    *,
    customer: str = "regular",
    coupon: str | None = None,
    shipping: str = "std",
) -> Decimal:
    """The amount to charge: sum of line totals -> customer discount -> coupon ->
    + shipping (based on the discounted amount) -> to_money. No items -> PricingError
    ("at least one item")."""
    # TODO (milestone 4)
    raise NotImplementedError("order_total")


def price_cart(
    cart: Iterable[Mapping[str, Any]],
    customer: str = "regular",
    coupon: str | None = None,
    shipping: str = "std",
) -> Decimal:
    """Drop-in replacement for legacy_pricing.calc(cart, cust, code, ship).

    Convert each entry with LineItem.from_dict; prefix errors with "cart item #N: "
    (and reject entries that are not dictionaries: "must be a dictionary").
    Must not import or call legacy_pricing.
    """
    # TODO (milestone 4)
    raise NotImplementedError("price_cart")
