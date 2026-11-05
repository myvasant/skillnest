# Testing legacy code (starter kit)

Your team has inherited the pricing code of a web shop: one long function, float money,
magic numbers, a global list and no tests at all. Nobody dares to touch it. In this project you
make it safe to change: first pin down what it does with **characterisation tests**, then
**refactor** it into small, typed, tested functions, and only then fix its bugs, one deliberate,
tested decision at a time. Standard library only.

## The problem

`legacy_pricing.calc(cart, cust, code=None, ship="std")` prices an order:

* per line: `price * qty`, 5% off from 10 items, then VAT (books 0%, food 5%, everything
  else 20%, although a comment says 15%);
* then the customer discount (`member` 10%, `staff` 30%), the coupon (`SAVE10` 10% off, `FLAT5`
  5 off orders above 50) and shipping (`std` 4.99, free from 50; `express` 12.50);
* it returns `round(total, 2)` as a float and appends every order to a global `ORDERS` list.

It also does things nobody asked for, and some callers may depend on them:

```python
>>> calc([{"sku": "B", "price": 30.0, "qty": 1, "cat": "books"}], "regular", None, "EXPRESS")
30.0       # an unknown shipping method ships for free
>>> calc([{"sku": "R", "price": 20.0, "qty": -3, "cat": "books"}], "regular")
-55.01     # negative quantities give negative totals
>>> calc([], "regular")
4.99       # an empty order still costs shipping
>>> calc([{"sku": "SW", "price": 0.1, "qty": 3, "cat": "food"}], "regular", None, "express")
12.81      # the exact total is 12.815; binary floats round it down
```

Your job is to produce `pricing_engine.py`: the same rules as small pure functions with named
constants, `Decimal` money and clear errors, proven equal to the legacy code for valid orders,
with each intentional change written down and tested.

## What's in this folder

| Path | Purpose |
|---|---|
| `starter/legacy_pricing.py` | The legacy code. **Identical** in `starter/` and `solution/`. Do not edit it. |
| `starter/pricing_engine.py` | Your refactoring target: names, signatures, docstrings and TODOs; functions raise `NotImplementedError`. |
| `solution/pricing_engine.py` | The reference refactoring. Try the milestones yourself first. |
| `tests/test_legacy_pricing.py` | 36 characterisation tests of the legacy code (milestones 1 and 2). They pass from the start: they are the reference answer for your own characterisation tests. |
| `tests/test_pricing_engine.py` | 156 tests of the refactored API (milestones 3 to 5), including a 72-case equivalence grid against the legacy code. |
| `conftest.py` | Makes the tests import `starter/` (default) or `solution/` (`GW_TARGET=solution`). |
| `requirements.txt` | Only `pytest`. `coverage` is optional (see below). |

## Setup

Run these commands from inside this folder (`projects/testing-legacy-code`).

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
once, or skip activation and call `.\.venv\Scripts\python.exe` directly.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running the tests

```bash
python -m pytest                    # everything, against starter/
python -m pytest -k Milestone3      # one milestone
python -m pytest tests/test_my_characterisation.py   # just your own tests
```

Compare with the reference solution:

```powershell
$env:GW_TARGET="solution"; python -m pytest
Remove-Item Env:GW_TARGET
```

```bash
GW_TARGET=solution python -m pytest
```

At the start, the 36 legacy tests pass and the `pricing_engine` tests fail. That is expected:
the legacy code already exists, the refactored code does not.

### Optional: coverage

Coverage shows which lines your tests never run. It is not needed for the project and is not
installed by `requirements.txt`:

```bash
python -m pip install coverage
python -m coverage run --branch --source=starter -m pytest
python -m coverage report -m        # missing line numbers per file
```

Aim for 100% line and branch coverage of `pricing_engine.py`, but remember that coverage only
proves a line ran, not that a test would notice if it were wrong. That is what the boundary
tests in milestone 5 are for.

## The workflow

1. **Characterise.** Call the legacy code with many inputs and write down what it returns, even
   when it looks wrong. A characterisation test asserts the *current* behaviour.
2. **Refactor in small steps.** Extract one rule at a time into `pricing_engine.py` (bulk
   discount, tax, customer discount, coupon, shipping, rounding), each with its own tests, and
   keep every test green after every step.
3. **Prove equivalence.** Compare the new code with the legacy code over a grid of valid orders
   (a *golden master*). Any difference is either a bug in your refactoring or a decision.
4. **Change behaviour deliberately.** Fix the quirks one at a time, each with a test that names
   the change, and record it in the module docstring so the next developer knows it was intended.

Never change behaviour and structure in the same step: if a test fails you will not know which
of the two broke it.

## Milestones

1. **Characterisation tests** (`-k Milestone1`). Create `tests/test_my_characterisation.py` and
   write at least 15 tests of `legacy_pricing.calc`: one per rule (VAT per category, bulk
   discount, customer types, coupons, shipping), the return type, the global `ORDERS` list
   (use `monkeypatch.setattr(legacy_pricing, "ORDERS", [])` so tests stay independent) and every
   quirk you can find. Get the expected numbers by *running* the code, then compare with
   `TestMilestone1Characterisation`.
2. **Test design** (`-k Milestone2`). Rewrite your tests in a fixture-based style: a fixture that
   builds carts, a `@pytest.mark.parametrize` golden-master table with readable `ids`, and
   `pytest.raises` for the errors the legacy code raises today (`KeyError`, `TypeError`).
   Compare with `TestMilestone2FixtureStyle`.
3. **Extract pure functions** (`-k Milestone3`). Implement `to_decimal`, `to_money`, `LineItem`
   (validation and `from_dict`), `tax_rate`, `apply_bulk_discount`, `line_total`,
   `apply_customer_discount`, `apply_coupon` and `shipping_cost` in `starter/pricing_engine.py`,
   with named constants and read-only tables (`types.MappingProxyType`), and no module-level
   lists or dicts.
4. **Equivalence and deliberate fixes** (`-k Milestone4`). Implement `order_total` and
   `price_cart`. The tests compare `price_cart` with `legacy_pricing.calc` on 72 valid orders
   (they must be equal to the cent), then check each deliberate change: half-up rounding
   (12.815 becomes 12.82), `PricingError` for unknown shipping methods, coupons and customer
   types, invalid quantities and prices, and empty carts, and no global order log.
5. **Boundaries** (`-k Milestone5`). Make sure the boundary tests pass: 9 versus 10 items, an
   order of exactly 50.00 versus 50.01 for `FLAT5`, 49.99 versus 50.00 for free shipping, and
   stacked discounts. Each pair would catch a mutation such as `>` becoming `>=`. Optionally,
   measure coverage (above) and add tests until `pricing_engine.py` is fully covered.

## Security notes

* **Validate money inputs.** The legacy code accepts negative quantities, which in a real shop
  becomes a refund exploit. The new code rejects quantities below 1 and negative prices before
  doing any arithmetic.
* **Fail closed.** An unknown shipping method or coupon used to mean "free" or "ignored". Raising
  `PricingError` stops a typo or a tampered request from silently changing the price.
* **Never use binary floats for money.** `Decimal` built from strings, rounded once at the end,
  gives the exact cents an accountant expects.
* **No hidden global state.** The legacy `ORDERS` list grows forever and is shared by every
  caller (in a web server, by every request and thread). The new code keeps no state at all.
