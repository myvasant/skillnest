"""Order pricing, refactored from ``legacy_pricing.calc``.

The business rules are unchanged: per line, quantity x price, a 5% bulk discount from
10 items, then VAT by category (books 0%, food 5%, everything else 20%); then the
customer discount (member 10%, staff 30%), the coupon (SAVE10: 10% off; FLAT5: 5 off
orders strictly above 50) and shipping (standard 4.99, free from 50; express 12.50).

What changed is the shape: small pure functions, named constants, ``Decimal`` money
and explicit errors. Deliberate behaviour changes, each pinned by a test:

1. Totals are rounded half-up to the cent. (Legacy used float ``round()``, so an exact
   12.815 became 12.81.)
2. Unknown customer types, coupon codes and shipping methods raise PricingError.
   (Legacy silently ignored them: shipping "EXPRESS" meant free shipping.)
3. Quantities must be whole numbers of at least 1 and prices zero or more.
   (Legacy accepted negative quantities and produced negative totals.)
4. An empty order raises PricingError. (Legacy charged 4.99 shipping for nothing.)
5. No global state: pricing an order does not append to a module-level list, and the
   rate tables are read-only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

CENT = Decimal("0.01")
ZERO = Decimal("0")

BULK_MIN_QUANTITY = 10
BULK_DISCOUNT = Decimal("0.05")

DEFAULT_CATEGORY = "other"
STANDARD_TAX_RATE = Decimal("0.20")
TAX_RATES: Mapping[str, Decimal] = MappingProxyType({"books": ZERO, "food": Decimal("0.05")})

CUSTOMER_DISCOUNTS: Mapping[str, Decimal] = MappingProxyType(
    {"regular": ZERO, "member": Decimal("0.10"), "staff": Decimal("0.30")}
)

SAVE10_RATE = Decimal("0.10")
FLAT5_AMOUNT = Decimal("5")
FLAT5_MINIMUM = Decimal("50")  # the order must be strictly above this amount

FREE_SHIPPING_MINIMUM = Decimal("50")  # standard shipping is free from this amount
SHIPPING_RATES: Mapping[str, Decimal] = MappingProxyType(
    {"std": Decimal("4.99"), "express": Decimal("12.50")}
)


class PricingError(ValueError):
    """The order cannot be priced; the message says why."""


def to_decimal(value: Any, field: str = "value") -> Decimal:
    """Convert an int, numeric string, float or Decimal to a finite Decimal.

    Floats go through ``str()`` first, so ``0.1`` becomes ``Decimal("0.1")`` rather than
    ``Decimal("0.1000000000000000055511151231257827021181583404541015625")``.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        raise PricingError(f"{field} must be a number, not {value!r}")
    try:
        result = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    except InvalidOperation:
        raise PricingError(f"{field} must be a number, not {value!r}") from None
    if not result.is_finite():
        raise PricingError(f"{field} must be a finite number, not {value!r}")
    return result


def to_money(amount: Decimal) -> Decimal:
    """Round to whole cents, halves away from zero: 2.675 -> 2.68, 2.665 -> 2.67."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineItem:
    """One cart line. ``price`` is the unit price before tax."""

    sku: str
    price: Decimal
    quantity: int
    category: str = DEFAULT_CATEGORY

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price < 0:
            raise PricingError(f"price of {self.sku!r} must be a Decimal of zero or more, not {self.price!r}")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 1:
            raise PricingError(
                f"quantity of {self.sku!r} must be a whole number of at least 1, not {self.quantity!r}"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LineItem:
        """Build an item from a legacy cart entry ``{"sku", "price", "qty", "cat"?}``."""
        for key in ("sku", "price", "qty"):
            if key not in data:
                raise PricingError(f"cart item is missing {key!r}")
        return cls(
            sku=str(data["sku"]),
            price=to_decimal(data["price"], "price"),
            quantity=data["qty"],
            category=data.get("cat") or DEFAULT_CATEGORY,
        )


def tax_rate(category: str) -> Decimal:
    """VAT rate for a category: books 0, food 0.05, anything else 0.20."""
    return TAX_RATES.get(category, STANDARD_TAX_RATE)


def apply_bulk_discount(amount: Decimal, quantity: int) -> Decimal:
    """Take 5% off a line of BULK_MIN_QUANTITY (10) or more items."""
    return amount * (1 - BULK_DISCOUNT) if quantity >= BULK_MIN_QUANTITY else amount


def line_total(item: LineItem) -> Decimal:
    """Price x quantity, bulk discount, then VAT. Not rounded: rounding happens once, at the end."""
    net = apply_bulk_discount(item.price * item.quantity, item.quantity)
    return net * (1 + tax_rate(item.category))


def apply_customer_discount(amount: Decimal, customer: str) -> Decimal:
    """Apply the discount for ``customer`` ("regular", "member" or "staff")."""
    try:
        rate = CUSTOMER_DISCOUNTS[customer]
    except KeyError:
        known = ", ".join(sorted(CUSTOMER_DISCOUNTS))
        raise PricingError(f"unknown customer type {customer!r}; expected one of: {known}") from None
    return amount * (1 - rate)


def apply_coupon(amount: Decimal, code: str | None) -> Decimal:
    """Apply a coupon: None (no coupon), "SAVE10" or "FLAT5" (only above 50)."""
    if code is None:
        return amount
    if code == "SAVE10":
        return amount - amount * SAVE10_RATE
    if code == "FLAT5":
        return amount - FLAT5_AMOUNT if amount > FLAT5_MINIMUM else amount
    raise PricingError(f"unknown coupon code {code!r}")


def shipping_cost(amount: Decimal, method: str) -> Decimal:
    """Shipping for an order worth ``amount``: "std" (free from 50) or "express"."""
    if method not in SHIPPING_RATES:
        known = " or ".join(SHIPPING_RATES)
        raise PricingError(f"unknown shipping method {method!r}; expected {known}")
    if method == "std" and amount >= FREE_SHIPPING_MINIMUM:
        return ZERO
    return SHIPPING_RATES[method]


def order_total(
    items: Iterable[LineItem],
    *,
    customer: str = "regular",
    coupon: str | None = None,
    shipping: str = "std",
) -> Decimal:
    """The amount to charge, in whole cents."""
    lines = list(items)
    if not lines:
        raise PricingError("an order needs at least one item")
    subtotal = sum((line_total(item) for item in lines), ZERO)
    discounted = apply_coupon(apply_customer_discount(subtotal, customer), coupon)
    return to_money(discounted + shipping_cost(discounted, shipping))


def price_cart(
    cart: Iterable[Mapping[str, Any]],
    customer: str = "regular",
    coupon: str | None = None,
    shipping: str = "std",
) -> Decimal:
    """Drop-in replacement for ``legacy_pricing.calc(cart, cust, code, ship)``.

    Takes the same arguments (legacy cart dictionaries), returns a Decimal and raises
    PricingError instead of guessing.
    """
    items: list[LineItem] = []
    for number, entry in enumerate(cart, start=1):
        if not isinstance(entry, Mapping):
            raise PricingError(f"cart item #{number} must be a dictionary, not {entry!r}")
        try:
            items.append(LineItem.from_dict(entry))
        except PricingError as exc:
            raise PricingError(f"cart item #{number}: {exc}") from None
    return order_total(items, customer=customer, coupon=coupon, shipping=shipping)
