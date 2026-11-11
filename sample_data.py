"""Sample e-commerce dataset (customers, orders -> invoices, expenses).

Primary source: the free DummyJSON API (https://dummyjson.com) - realistic users,
shopping carts and products. If the API can't be reached, a deterministic offline
generator produces a similar online-store dataset so the demo always works.

All sample rows get ids starting with "sample-" so they can be removed later.
"""

from __future__ import annotations

import json
import random
import urllib.request
from datetime import date, timedelta

API = "https://dummyjson.com"
USD_TO_INR = 83.0
PREFIX = "sample-"


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers={"User-Agent": "invoice-tracker-demo"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https host
        return json.load(resp)


def _sid(kind: str, n) -> str:
    return f"{PREFIX}{kind}-{n}"


def _spread_dates(rng: random.Random, n: int, days: int = 365) -> list[date]:
    today = date.today()
    return sorted(today - timedelta(days=rng.randint(0, days)) for _ in range(n))


def _status_for(rng: random.Random, issue: date, due: date) -> tuple[str, date | None]:
    """Older invoices are mostly paid; recent ones mostly pending."""
    age = (date.today() - issue).days
    roll = rng.random()
    if roll < 0.04:
        return "Cancelled", None
    if age > 45 and roll < 0.92 or age <= 45 and roll < 0.45:
        return "Paid", min(date.today(), issue + timedelta(days=rng.randint(1, 25)))
    return "Pending", None


def _invoices_from_orders(orders, customers, rng, tax_rate, terms, prefix) -> list[dict]:
    by_id = {c["_ext"]: c for c in customers}
    dates = _spread_dates(rng, len(orders))
    out = []
    for n, (order, issue) in enumerate(zip(orders, dates), start=1):
        cust = by_id.get(order["user"]) or rng.choice(customers)
        items = [{"description": p["title"], "quantity": float(p["quantity"]),
                  "price": round(float(p["price"]), 2), "tax_rate": tax_rate} for p in order["products"]]
        subtotal = sum(i["quantity"] * i["price"] for i in items)
        tax = subtotal * tax_rate / 100
        discount = round(float(order.get("discount", 0)), 2)
        due = issue + timedelta(days=terms)
        status, paid = _status_for(rng, issue, due)
        out.append({
            "id": _sid("inv", n), "number": f"{prefix}{n:04d}",
            "customer_id": cust["id"], "customer_name": cust["name"], "customer_email": cust["email"],
            "customer_address": cust["address"], "issue_date": issue.isoformat(), "due_date": due.isoformat(),
            "status": status, "paid_date": paid.isoformat() if paid else None, "items": items,
            "discount": discount, "subtotal": round(subtotal, 2), "tax": round(tax, 2),
            "total": round(subtotal + tax - discount, 2), "notes": f"Online order #{order['ref']}",
        })
    return out


def _expenses(rng: random.Random, scale: float) -> list[dict]:
    templates = [
        ("Rent", "WeWork", "Warehouse & office rent", 45000, "Bank Transfer", 30),
        ("Salary", "Payroll", "Staff salaries", 120000, "Bank Transfer", 30),
        ("Utilities", "State Electricity Board", "Electricity bill", 6500, "UPI", 30),
        ("Utilities", "Airtel", "Broadband & phones", 2400, "Credit Card", 30),
        ("Software", "Shopify", "Store subscription", 2500, "Credit Card", 30),
        ("Software", "Google Workspace", "Email & docs", 1800, "Credit Card", 30),
        ("Marketing", "Google Ads", "Search campaign", 18000, "Credit Card", 14),
        ("Marketing", "Meta Ads", "Social campaign", 12000, "Credit Card", 14),
        ("Travel", "Delhivery", "Outbound shipping", 9000, "Bank Transfer", 7),
        ("Office Supplies", "Packaging Co.", "Boxes, tape & labels", 4500, "UPI", 21),
        ("Food", "Swiggy", "Team lunch", 2200, "UPI", 20),
        ("Taxes", "GST Portal", "GST payment", 25000, "Bank Transfer", 30),
    ]
    out, n, today = [], 0, date.today()
    for cat, vendor, desc, base, method, every in templates:
        d = today - timedelta(days=365)
        while d <= today:
            n += 1
            amount = round(base * scale * rng.uniform(0.8, 1.2), 2)
            out.append({"id": _sid("exp", n), "date": d.isoformat(), "category": cat, "vendor": vendor,
                        "description": desc, "amount": amount, "payment_method": method})
            d += timedelta(days=every + rng.randint(-2, 2))
    return out


# ---------------------------------------------------------------- sources

def _from_api(rng: random.Random, usd_factor: float) -> tuple[list[dict], list[dict]]:
    users = _get("/users?limit=0&select=firstName,lastName,email,phone,address,company")["users"]
    carts = _get("/carts?limit=0")["carts"]
    customers = []
    for u in users:
        a = u.get("address") or {}
        customers.append({
            "id": _sid("cust", u["id"]), "_ext": u["id"],
            "name": f"{u['firstName']} {u['lastName']}", "email": u["email"], "phone": u.get("phone", ""),
            "company": (u.get("company") or {}).get("name", ""), "tax_id": "",
            "address": ", ".join(x for x in [a.get("address"), a.get("city"), a.get("state"),
                                             a.get("postalCode"), a.get("country")] if x),
        })
    orders = []
    for c in carts:
        products = [{"title": p["title"], "quantity": p["quantity"], "price": p["price"] * usd_factor}
                    for p in c["products"]]
        discount = (c["total"] - c["discountedTotal"]) * usd_factor
        orders.append({"user": c["userId"], "ref": f"DJ-{c['id']}", "products": products, "discount": discount})
    return customers, orders


FIRST = ["Aarav", "Vivaan", "Aditya", "Ananya", "Diya", "Ishaan", "Kavya", "Rohan", "Saanvi", "Arjun",
         "Meera", "Kabir", "Priya", "Neha", "Rahul", "Sneha", "Vikram", "Pooja", "Karan", "Riya",
         "Emily", "James", "Olivia", "Liam", "Sophia", "Noah", "Ava", "Ethan", "Mia", "Lucas"]
LAST = ["Sharma", "Verma", "Gupta", "Iyer", "Reddy", "Patel", "Nair", "Mehta", "Kapoor", "Singh",
        "Das", "Joshi", "Bose", "Khan", "Rao", "Smith", "Johnson", "Brown", "Williams", "Garcia"]
CITIES = [("Mumbai", "Maharashtra", "400001"), ("Bengaluru", "Karnataka", "560001"),
          ("New Delhi", "Delhi", "110001"), ("Hyderabad", "Telangana", "500001"),
          ("Chennai", "Tamil Nadu", "600001"), ("Pune", "Maharashtra", "411001"),
          ("Kolkata", "West Bengal", "700001"), ("Ahmedabad", "Gujarat", "380001"),
          ("Jaipur", "Rajasthan", "302001"), ("Kochi", "Kerala", "682001")]
STREETS = ["MG Road", "Park Street", "Linking Road", "Brigade Road", "Anna Salai", "FC Road", "Banjara Hills"]
CATALOG = [  # (title, INR price)
    ("Wireless Bluetooth Earbuds", 1999), ("Smartphone 128GB", 18999), ("USB-C Fast Charger 65W", 1499),
    ("Laptop Backpack", 1299), ("Mechanical Keyboard", 3499), ("Wireless Mouse", 799),
    ("27\" 4K Monitor", 24999), ("Smart Watch", 4999), ("Portable Power Bank 20000mAh", 1799),
    ("Noise Cancelling Headphones", 12999), ("Stainless Steel Water Bottle", 549),
    ("Non-stick Cookware Set", 2899), ("Air Fryer 4L", 5499), ("Running Shoes", 3299),
    ("Cotton T-Shirt (Pack of 3)", 999), ("Yoga Mat", 899), ("LED Desk Lamp", 1199),
    ("Paperback Novel", 399), ("Coffee Beans 1kg", 1150), ("Kindle-style E-Reader", 9999),
    ("HDMI Cable 2m", 349), ("External SSD 1TB", 7499), ("Smart Bulb (Pack of 2)", 1299),
    ("Fitness Band", 2499), ("Office Chair", 8999), ("Bedsheet Set", 1499),
]


def _offline(rng: random.Random, inr_factor: float) -> tuple[list[dict], list[dict]]:
    customers, used = [], set()
    for n in range(1, 41):
        while True:
            f, l = rng.choice(FIRST), rng.choice(LAST)
            if (f, l) not in used:
                used.add((f, l))
                break
        city, state, pin = rng.choice(CITIES)
        customers.append({
            "id": _sid("cust", n), "_ext": n, "name": f"{f} {l}",
            "email": f"{f.lower()}.{l.lower()}{n}@example.com",
            "phone": f"+91 9{rng.randint(100000000, 999999999)}",
            "company": rng.choice(["", "", "", f"{l} Traders", f"{l} & Co.", "Freelancer"]), "tax_id": "",
            "address": f"{rng.randint(1, 250)}, {rng.choice(STREETS)}, {city}, {state} {pin}, India",
        })
    orders = []
    for n in range(1, 181):
        picks = rng.sample(CATALOG, rng.randint(1, 4))
        products = [{"title": t, "quantity": rng.choice([1, 1, 1, 2, 3]), "price": p * inr_factor} for t, p in picks]
        gross = sum(p["quantity"] * p["price"] for p in products)
        orders.append({"user": rng.randint(1, 40), "ref": f"OD-{rng.randint(10**8, 10**9 - 1)}",
                       "products": products, "discount": round(gross * rng.choice([0, 0, 0.05, 0.1]), 2)})
    return customers, orders


def build_dataset(currency: str = "₹", tax_rate: float = 18.0, terms: int = 15,
                  prefix: str = "ORD-", use_api: bool = True, seed: int = 42) -> tuple[dict, str]:
    """Return (payload for db.import_all, source description)."""
    rng = random.Random(seed)
    to_inr = currency == "₹"
    source = "offline generator"
    customers = orders = None
    if use_api:
        try:
            customers, orders = _from_api(rng, USD_TO_INR if to_inr else 1.0)
            source = "DummyJSON API (dummyjson.com)"
        except Exception:  # noqa: BLE001 - network may be blocked; fall back
            customers = None
    if not customers:
        customers, orders = _offline(rng, 1.0 if to_inr else 1 / USD_TO_INR)
    invoices = _invoices_from_orders(orders, customers, rng, tax_rate, terms, prefix)
    expenses = _expenses(rng, 1.0)
    # Scale running costs so the sample business is realistically profitable (~65% cost ratio).
    revenue = sum(i["subtotal"] for i in invoices if i["status"] != "Cancelled")
    spent = sum(e["amount"] for e in expenses) or 1
    factor = 0.65 * revenue / spent
    for e in expenses:
        e["amount"] = round(e["amount"] * factor, 2)
    for c in customers:
        c.pop("_ext", None)
    return {"customers": customers, "invoices": invoices, "expenses": expenses}, source


# ---------------------------------------------------------------- Amazon Seller Central import

def parse_amazon_orders(raw: bytes, tax_rate_fallback: float = 0.0, terms: int = 0) -> dict:
    """Convert an Amazon Seller Central order report into a db.import_all payload.

    Accepts the "All Orders" / "Order report" export (tab- or comma-separated) with columns such as
    amazon-order-id, purchase-date, order-status, product-name, quantity, item-price, item-tax,
    buyer-name, buyer-email, ship-city, ship-state, ship-postal-code, ship-country.
    Rows that share an order id become one invoice with several line items.
    """
    import csv
    import hashlib
    import io

    text = raw.decode("utf-8-sig", errors="replace")
    dialect = "excel-tab" if text.split("\n", 1)[0].count("\t") > text.split("\n", 1)[0].count(",") else "excel"
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    if not rows:
        raise ValueError("The file has no rows.")
    norm = [{(k or "").strip().lower().replace("_", "-").replace(" ", "-"): (v or "").strip()
             for k, v in r.items()} for r in rows]
    if "amazon-order-id" not in norm[0] and "order-id" not in norm[0]:
        raise ValueError("Missing 'amazon-order-id' column - is this an Amazon order report?")

    def num(v):
        try:
            return float(str(v).replace(",", "") or 0)
        except ValueError:
            return 0.0

    def key(*parts):
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]

    customers, orders = {}, {}
    for r in norm:
        oid = r.get("amazon-order-id") or r.get("order-id")
        if not oid or (r.get("order-status", "").lower() == "cancelled" and not r.get("product-name")):
            continue
        place = ", ".join(x for x in [r.get("ship-city"), r.get("ship-state"),
                                      r.get("ship-postal-code"), r.get("ship-country")] if x)
        name = r.get("buyer-name") or r.get("recipient-name") or f"Amazon customer ({r.get('ship-city') or 'unknown'})"
        email = r.get("buyer-email") or f"{key(name, place)}@marketplace.amazon"
        cid = "amzn-c-" + key(email.lower())
        customers.setdefault(cid, {"id": cid, "name": name, "email": email, "phone": r.get("buyer-phone-number", ""),
                                   "company": "", "tax_id": "", "address": place})
        qty = num(r.get("quantity") or r.get("quantity-purchased") or 1) or 1
        line_total = num(r.get("item-price"))
        tax = num(r.get("item-tax"))
        rate = round(tax / line_total * 100, 2) if line_total else tax_rate_fallback
        o = orders.setdefault(oid, {"cid": cid, "date": (r.get("purchase-date") or "")[:10],
                                    "status": r.get("order-status", ""), "items": [], "discount": 0.0})
        o["items"].append({"description": r.get("product-name") or r.get("sku") or "Item",
                           "quantity": qty, "price": round(line_total / qty, 2), "tax_rate": rate})
        o["discount"] += num(r.get("item-promotion-discount")) + num(r.get("ship-promotion-discount"))

    invoices = []
    for oid, o in orders.items():
        c = customers[o["cid"]]
        try:
            issue = date.fromisoformat(o["date"])
        except ValueError:
            issue = date.today()
        st = o["status"].lower()
        status = "Cancelled" if "cancel" in st else "Pending" if st in ("pending", "unshipped") else "Paid"
        subtotal = sum(i["quantity"] * i["price"] for i in o["items"])
        tax = sum(i["quantity"] * i["price"] * i["tax_rate"] / 100 for i in o["items"])
        invoices.append({
            "id": "amzn-i-" + key(oid), "number": oid, "customer_id": c["id"], "customer_name": c["name"],
            "customer_email": c["email"], "customer_address": c["address"], "issue_date": issue.isoformat(),
            "due_date": (issue + timedelta(days=terms)).isoformat(), "status": status,
            "paid_date": issue.isoformat() if status == "Paid" else None, "items": o["items"],
            "discount": round(o["discount"], 2), "subtotal": round(subtotal, 2), "tax": round(tax, 2),
            "total": round(subtotal + tax - o["discount"], 2), "notes": "Imported from Amazon Seller Central",
        })
    return {"customers": list(customers.values()), "invoices": invoices, "expenses": []}
