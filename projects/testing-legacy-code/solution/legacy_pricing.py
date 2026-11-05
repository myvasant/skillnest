"""Order pricing for the web shop.

DO NOT TOUCH - this works!! (last change 2019, ask Dave)

NOTE FOR LEARNERS: this file is the "legacy code" of the project. It is messy on
purpose (single-letter names, magic numbers, float money, a global list, an out-of-date
comment, silent fallbacks) and it is identical in starter/ and solution/. Do not fix
it here: pin its behaviour with characterisation tests, then rebuild it cleanly in
pricing_engine.py.
"""

ORDERS = []  # every order we priced, for the daily report


def calc(cart, cust, code=None, ship="std"):
    # cart = list of {"sku": ..., "price": ..., "qty": ..., "cat": ...}
    t = 0
    for i in cart:
        p = i["price"] * i["qty"]
        if i["qty"] >= 10:
            p = p * 0.95  # bulk
        if i.get("cat") == "books":
            p = p  # no VAT on books
        elif i.get("cat") == "food":
            p = p * 1.05
        else:
            p = p * 1.2  # 15% VAT
        t = t + p
    if cust == "member":
        t = t * 0.9
    elif cust == "staff":
        t = t * 0.7
    elif cust == "vip":
        pass  # vip discount removed in 2018?
    if code != None:  # noqa: E711 - legacy style, kept on purpose for the exercise
        if code == "SAVE10":
            t = t - t * 0.1
        elif code == "FLAT5":
            if t > 50:
                t = t - 5
    if ship == "std":
        if t < 50:
            t = t + 4.99
    elif ship == "express":
        t = t + 12.5
    ORDERS.append({"cust": cust, "total": round(t, 2)})
    return round(t, 2)


def calc_many(orders):
    # orders = list of (cart, cust, code, ship)
    res = []
    for o in orders:
        res.append(calc(o[0], o[1], o[2], o[3]))
    return res
