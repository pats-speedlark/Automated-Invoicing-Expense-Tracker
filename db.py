"""Storage layer for the Invoicing & Expense Tracker.

Uses SQLAlchemy so the same code works with:
  * PostgreSQL  - set the DATABASE_URL environment variable
                  (Railway sets this automatically when you add a Postgres service)
  * SQLite      - default fallback, stored in data/finance.db
"""

from __future__ import annotations

import csv
import json
import os
import uuid
from datetime import date, datetime
from typing import Any

import streamlit as st
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

DATA_DIR = os.environ.get("DATA_DIR", "data")

metadata = MetaData()

settings_table = Table(
    "settings",
    metadata,
    Column("key", String(100), primary_key=True),
    Column("value", Text),
)

customers_table = Table(
    "customers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("email", String(200), nullable=False),
    Column("phone", String(50)),
    Column("company", String(200)),
    Column("tax_id", String(50)),
    Column("address", Text),
    Column("created_at", DateTime, default=datetime.utcnow),
)

invoices_table = Table(
    "invoices",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("number", String(50), nullable=False, unique=True),
    Column("customer_id", String(36)),
    Column("customer_name", String(200)),
    Column("customer_email", String(200)),
    Column("customer_address", Text),
    Column("issue_date", Date),
    Column("due_date", Date),
    Column("status", String(20), default="Pending"),
    Column("items", JSON),
    Column("discount", Float, default=0.0),
    Column("subtotal", Float, default=0.0),
    Column("tax", Float, default=0.0),
    Column("total", Float, default=0.0),
    Column("notes", Text),
    Column("paid_date", Date),
    Column("created_at", DateTime, default=datetime.utcnow),
)

expenses_table = Table(
    "expenses",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("date", Date),
    Column("category", String(50)),
    Column("vendor", String(200)),
    Column("description", Text),
    Column("amount", Float, nullable=False),
    Column("payment_method", String(50)),
    Column("created_at", DateTime, default=datetime.utcnow),
)

DEFAULT_SETTINGS = {
    "business_name": "My Business",
    "business_email": "",
    "business_phone": "",
    "business_address": "",
    "business_tax_id": "",
    "currency": "₹",
    "default_tax_rate": "18",
    "invoice_prefix": "INV-",
    "next_invoice_number": "1001",
    "payment_terms_days": "15",
    "invoice_footer": "Thank you for your business!",
}

EXPENSE_CATEGORIES = [
    "Food", "Travel", "Rent", "Shopping", "Utilities", "Salary",
    "Software", "Marketing", "Office Supplies", "Taxes", "Other",
]
PAYMENT_METHODS = ["Cash", "UPI", "Bank Transfer", "Credit Card", "Debit Card", "Cheque", "Other"]
INVOICE_STATUSES = ["Draft", "Pending", "Paid", "Cancelled"]


# ---------------------------------------------------------------- engine

def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        os.makedirs(DATA_DIR, exist_ok=True)
        return f"sqlite:///{os.path.join(DATA_DIR, 'finance.db')}"
    # Railway / Heroku style URLs -> SQLAlchemy psycopg3 driver
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    url = _database_url()
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["connect_args"] = {"connect_timeout": 10}
    engine = create_engine(url, **kwargs)
    metadata.create_all(engine)
    _seed_settings(engine)
    _import_legacy_files(engine)
    return engine


def backend_name() -> str:
    return "PostgreSQL" if get_engine().dialect.name == "postgresql" else "SQLite (local file)"


def _new_id() -> str:
    return uuid.uuid4().hex


def _clean(row) -> dict:
    return dict(row._mapping)


# ---------------------------------------------------------------- settings

def _seed_settings(engine: Engine) -> None:
    with engine.begin() as conn:
        existing = {r.key for r in conn.execute(select(settings_table.c.key))}
        missing = [{"key": k, "value": v} for k, v in DEFAULT_SETTINGS.items() if k not in existing]
        if missing:
            conn.execute(insert(settings_table), missing)


def get_settings() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(select(settings_table)).all()
    data = dict(DEFAULT_SETTINGS)
    data.update({r.key: r.value for r in rows})
    return data


def save_settings(values: dict) -> None:
    with get_engine().begin() as conn:
        for key, value in values.items():
            res = conn.execute(
                update(settings_table).where(settings_table.c.key == key).values(value=str(value))
            )
            if res.rowcount == 0:
                conn.execute(insert(settings_table).values(key=key, value=str(value)))


def _next_invoice_number(conn) -> str:
    rows = {r.key: r.value for r in conn.execute(select(settings_table))}
    prefix = rows.get("invoice_prefix", DEFAULT_SETTINGS["invoice_prefix"])
    try:
        number = int(rows.get("next_invoice_number", DEFAULT_SETTINGS["next_invoice_number"]))
    except ValueError:
        number = 1001
    existing = {r.number for r in conn.execute(select(invoices_table.c.number))}
    while f"{prefix}{number}" in existing:
        number += 1
    conn.execute(
        update(settings_table)
        .where(settings_table.c.key == "next_invoice_number")
        .values(value=str(number + 1))
    )
    return f"{prefix}{number}"


# ---------------------------------------------------------------- customers

def list_customers() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(customers_table).order_by(customers_table.c.name)).all()
    return [_clean(r) for r in rows]


def email_exists(email: str, exclude_id: str | None = None) -> bool:
    email = email.strip().lower()
    return any(
        c["email"].lower() == email and c["id"] != exclude_id for c in list_customers()
    )


def add_customer(data: dict) -> str:
    cid = _new_id()
    with get_engine().begin() as conn:
        conn.execute(insert(customers_table).values(id=cid, created_at=datetime.utcnow(), **data))
    return cid


def update_customer(cid: str, data: dict) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(customers_table).where(customers_table.c.id == cid).values(**data))


def delete_customer(cid: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(customers_table).where(customers_table.c.id == cid))


# ---------------------------------------------------------------- invoices

def compute_totals(items: list[dict], discount: float) -> tuple[float, float, float]:
    subtotal = sum(float(i["quantity"]) * float(i["price"]) for i in items)
    tax = sum(
        float(i["quantity"]) * float(i["price"]) * float(i.get("tax_rate", 0)) / 100 for i in items
    )
    discount = min(max(float(discount or 0), 0.0), subtotal + tax)
    total = subtotal + tax - discount
    return round(subtotal, 2), round(tax, 2), round(total, 2)


def list_invoices() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(invoices_table).order_by(invoices_table.c.issue_date.desc(), invoices_table.c.created_at.desc())
        ).all()
    return [_clean(r) for r in rows]


def get_invoice(iid: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(invoices_table).where(invoices_table.c.id == iid)).first()
    return _clean(row) if row else None


def add_invoice(data: dict) -> dict:
    subtotal, tax, total = compute_totals(data["items"], data.get("discount", 0))
    iid = _new_id()
    with get_engine().begin() as conn:
        number = _next_invoice_number(conn)
        conn.execute(
            insert(invoices_table).values(
                id=iid, number=number, subtotal=subtotal, tax=tax, total=total,
                created_at=datetime.utcnow(), **data,
            )
        )
    return get_invoice(iid)


def update_invoice(iid: str, data: dict) -> None:
    if "items" in data:
        subtotal, tax, total = compute_totals(data["items"], data.get("discount", 0))
        data = {**data, "subtotal": subtotal, "tax": tax, "total": total}
    with get_engine().begin() as conn:
        conn.execute(update(invoices_table).where(invoices_table.c.id == iid).values(**data))


def set_invoice_status(iid: str, status: str) -> None:
    update_invoice(iid, {"status": status, "paid_date": date.today() if status == "Paid" else None})


def delete_invoice(iid: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(invoices_table).where(invoices_table.c.id == iid))


# ---------------------------------------------------------------- expenses

def list_expenses() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(expenses_table).order_by(expenses_table.c.date.desc(), expenses_table.c.created_at.desc())
        ).all()
    return [_clean(r) for r in rows]


def add_expense(data: dict) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(expenses_table).values(id=_new_id(), created_at=datetime.utcnow(), **data))


def update_expense(eid: str, data: dict) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(expenses_table).where(expenses_table.c.id == eid).values(**data))


def delete_expense(eid: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(expenses_table).where(expenses_table.c.id == eid))


# ---------------------------------------------------------------- backup / restore

def _jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def export_all() -> str:
    payload = {
        "exported_at": datetime.utcnow().isoformat(),
        "settings": get_settings(),
        "customers": list_customers(),
        "invoices": list_invoices(),
        "expenses": list_expenses(),
    }
    return json.dumps(payload, default=_jsonable, indent=2, ensure_ascii=False)


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_dt(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return datetime.utcnow()


def import_all(payload: dict, replace: bool = False, engine: Engine | None = None) -> dict:
    """Import a backup produced by export_all(). Returns counts of inserted rows."""
    counts = {"customers": 0, "invoices": 0, "expenses": 0}
    with (engine or get_engine()).begin() as conn:
        if replace:
            for table in (invoices_table, expenses_table, customers_table):
                conn.execute(delete(table))
        existing_c = {r.id for r in conn.execute(select(customers_table.c.id))}
        existing_i = {r.id for r in conn.execute(select(invoices_table.c.id))}
        existing_n = {r.number for r in conn.execute(select(invoices_table.c.number))}
        existing_e = {r.id for r in conn.execute(select(expenses_table.c.id))}

        for c in payload.get("customers", []):
            if c.get("id") in existing_c:
                continue
            conn.execute(insert(customers_table).values(
                id=c.get("id") or _new_id(), name=c.get("name", ""), email=c.get("email", ""),
                phone=c.get("phone", ""), company=c.get("company", ""), tax_id=c.get("tax_id", ""),
                address=c.get("address", ""), created_at=_parse_dt(c.get("created_at")),
            ))
            counts["customers"] += 1

        for i in payload.get("invoices", []):
            if i.get("id") in existing_i or i.get("number") in existing_n:
                continue
            conn.execute(insert(invoices_table).values(
                id=i.get("id") or _new_id(), number=i["number"],
                customer_id=i.get("customer_id"), customer_name=i.get("customer_name"),
                customer_email=i.get("customer_email"), customer_address=i.get("customer_address"),
                issue_date=_parse_date(i.get("issue_date")), due_date=_parse_date(i.get("due_date")),
                status=i.get("status", "Pending"), items=i.get("items") or [],
                discount=float(i.get("discount") or 0), subtotal=float(i.get("subtotal") or 0),
                tax=float(i.get("tax") or 0), total=float(i.get("total") or 0),
                notes=i.get("notes", ""), paid_date=_parse_date(i.get("paid_date")),
                created_at=_parse_dt(i.get("created_at")),
            ))
            counts["invoices"] += 1

        for e in payload.get("expenses", []):
            if e.get("id") in existing_e:
                continue
            conn.execute(insert(expenses_table).values(
                id=e.get("id") or _new_id(), date=_parse_date(e.get("date")),
                category=e.get("category", "Other"), vendor=e.get("vendor", ""),
                description=e.get("description", ""), amount=float(e.get("amount") or 0),
                payment_method=e.get("payment_method", ""), created_at=_parse_dt(e.get("created_at")),
            ))
            counts["expenses"] += 1
    return counts


def _import_legacy_files(engine: Engine) -> None:
    """One-time migration of the old JSON/CSV files (data/*.json, data/expenses.csv)."""
    marker = os.path.join(DATA_DIR, ".legacy_imported")
    cust_f = os.path.join(DATA_DIR, "customers.json")
    inv_f = os.path.join(DATA_DIR, "invoices.json")
    exp_f = os.path.join(DATA_DIR, "expenses.csv")
    if os.path.exists(marker) or not any(os.path.exists(f) for f in (cust_f, inv_f, exp_f)):
        return

    def _load_json(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []

    customers = _load_json(cust_f) if os.path.exists(cust_f) else []
    by_email = {c.get("email", "").lower(): c for c in customers}
    invoices = []
    for old in _load_json(inv_f) if os.path.exists(inv_f) else []:
        qty, price, rate = float(old.get("quantity", 1)), float(old.get("price", 0)), float(old.get("tax_rate", 0))
        cust = by_email.get(str(old.get("email", "")).lower(), {})
        invoices.append({
            "number": old.get("id"), "customer_id": cust.get("id"),
            "customer_name": old.get("customer"), "customer_email": old.get("email"),
            "customer_address": cust.get("address", ""),
            "issue_date": old.get("date"), "due_date": old.get("date"),
            "status": old.get("status", "Pending"),
            "items": [{"description": old.get("description", ""), "quantity": qty, "price": price, "tax_rate": rate}],
            "subtotal": old.get("subtotal", qty * price), "tax": old.get("tax", 0),
            "total": old.get("total", 0),
        })
    expenses = []
    if os.path.exists(exp_f):
        with open(exp_f, newline="", encoding="utf-8") as fh:
            expenses = list(csv.DictReader(fh))

    import_all({"customers": customers, "invoices": invoices, "expenses": expenses}, engine=engine)
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(datetime.utcnow().isoformat())
    except OSError:
        pass


# ---------------------------------------------------------------- sample data

def has_sample_data() -> bool:
    with get_engine().connect() as conn:
        return conn.execute(
            select(customers_table.c.id).where(customers_table.c.id.like("sample-%")).limit(1)
        ).first() is not None


def load_sample_data(use_api: bool = True) -> tuple[dict, str]:
    from sample_data import build_dataset

    s = get_settings()
    payload, source = build_dataset(
        currency=s.get("currency", "₹"), tax_rate=float(s.get("default_tax_rate") or 18),
        terms=int(s.get("payment_terms_days") or 15), use_api=use_api,
    )
    return import_all(payload), source


def remove_sample_data() -> None:
    with get_engine().begin() as conn:
        for table in (invoices_table, expenses_table, customers_table):
            conn.execute(delete(table).where(table.c.id.like("sample-%")))
