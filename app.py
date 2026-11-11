"""Automated Invoicing & Expense Tracker - web app.

Run locally:   python start.py
Storage:       PostgreSQL when DATABASE_URL is set, otherwise SQLite (data/finance.db)
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

import db
from pdf_utils import generate_invoice_pdf

st.set_page_config(
    page_title="Invoicing & Expense Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="auto",
)

# ------------------------------------------------------------------ styling

st.markdown(
    """
    <style>
    /* Hide framework branding / developer chrome (menu, deploy button, status, footer) */
    #MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stToolbarActions"],
    [data-testid="stAppDeployButton"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
    .stDeployButton, .viewerBadge_container__1QSob {display: none !important; visibility: hidden !important;}
    header[data-testid="stHeader"] {background: transparent;}
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
    [data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128,128,128,.18);
        border-radius: 14px; padding: 14px 18px;
    }
    [data-testid="stMetricLabel"] p {font-size: .85rem; opacity: .8;}
    [data-testid="stMetricValue"] {font-size: 1.55rem; font-weight: 700;}
    .stButton button, .stDownloadButton button, .stFormSubmitButton button {
        border-radius: 10px; min-height: 2.6rem;
    }
    .badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:600;}
    .badge-Paid {background:#DCFCE7; color:#166534;}
    .badge-Pending {background:#FEF3C7; color:#92400E;}
    .badge-Overdue {background:#FEE2E2; color:#991B1B;}
    .badge-Draft {background:#E5E7EB; color:#374151;}
    .badge-Cancelled {background:#E5E7EB; color:#6B7280; text-decoration: line-through;}
    .muted {opacity:.7; font-size:.9rem;}

    /* Tablet: let column rows wrap into two per line */
    @media (max-width: 1024px) {
        .block-container {padding-left: 1.25rem; padding-right: 1.25rem;}
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: .75rem;}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: calc(50% - .75rem) !important; flex: 1 1 calc(50% - .75rem) !important;
        }
        [data-testid="stMetricValue"] {font-size: 1.3rem;}
    }
    /* Phone: one column, full-width buttons */
    @media (max-width: 640px) {
        .block-container {padding: 1rem .75rem 3rem;}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 100% !important; flex: 1 1 100% !important;
        }
        h1 {font-size: 1.6rem !important;}
        .stButton button, .stDownloadButton button, .stFormSubmitButton button {width: 100%;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ auth (optional)

def check_password() -> bool:
    """If APP_PASSWORD is set, require it before showing the app."""
    password = os.environ.get("APP_PASSWORD", "")
    if not password or st.session_state.get("authenticated"):
        return True
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title("🔒 Sign in")
        with st.form("login"):
            entered = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                if hmac.compare_digest(entered, password):
                    st.session_state.authenticated = True
                    st.rerun()
                st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ------------------------------------------------------------------ helpers

try:
    SETTINGS = db.get_settings()
except Exception as exc:  # noqa: BLE001 - show a friendly error instead of a crash loop
    st.error("Could not connect to the database. Check DATABASE_URL.")
    st.exception(exc)
    st.stop()

CUR = SETTINGS.get("currency", "₹")


def money(value) -> str:
    return f"{CUR}{float(value or 0):,.2f}"


def effective_status(inv: dict) -> str:
    if inv["status"] == "Pending" and inv.get("due_date") and inv["due_date"] < date.today():
        return "Overdue"
    return inv["status"]


def badge(status: str) -> str:
    return f'<span class="badge badge-{status}">{status}</span>'


def invoices_df(invoices: list[dict]) -> pd.DataFrame:
    if not invoices:
        return pd.DataFrame(columns=["number", "customer_name", "issue_date", "due_date", "total", "status"])
    df = pd.DataFrame(invoices)
    df["status"] = [effective_status(i) for i in invoices]
    df["issue_date"] = pd.to_datetime(df["issue_date"])
    df["due_date"] = pd.to_datetime(df["due_date"])
    return df


def expenses_df(expenses: list[dict]) -> pd.DataFrame:
    cols = ["id", "date", "category", "vendor", "description", "amount", "payment_method"]
    if not expenses:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(expenses)[cols]
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()


def chart(fig, height=340):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# ------------------------------------------------------------------ pages

def page_dashboard():
    st.title("📊 Dashboard")
    st.caption(f"Welcome back, {SETTINGS['business_name']} · {date.today():%A, %d %B %Y}")

    inv = invoices_df(db.list_invoices())
    exp = expenses_df(db.list_expenses())

    if inv.empty and exp.empty:
        with st.container(border=True):
            st.markdown("#### 👋 Getting started")
            st.write("Your books are empty. Add a customer and create an invoice, or explore the app "
                     "with a realistic sample online-store dataset.")
            if st.button("📦 Load sample data", type="primary"):
                with st.spinner("Fetching sample dataset…"):
                    counts, source = db.load_sample_data()
                st.toast(f"Loaded {counts['invoices']} invoices from {source}", icon="📦")
                st.rerun()

    income = inv.loc[inv.status == "Paid", "total"].astype(float).sum() if len(inv) else 0
    outstanding = inv.loc[inv.status.isin(["Pending", "Overdue"]), "total"].astype(float).sum() if len(inv) else 0
    overdue = inv.loc[inv.status == "Overdue", "total"].astype(float).sum() if len(inv) else 0
    spent = exp["amount"].sum() if len(exp) else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income received", money(income))
    c2.metric("Total expenses", money(spent))
    c3.metric("Outstanding", money(outstanding),
              delta=f"{money(overdue)} overdue" if overdue else None, delta_color="inverse")
    c4.metric("Net profit", money(income - spent))

    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Cash flow (last 12 months)")
        start = (pd.Timestamp.today().to_period("M") - 11).to_timestamp()
        months = pd.period_range(start, periods=12, freq="M")
        paid = inv[inv.status == "Paid"].copy() if len(inv) else inv
        inc_m = (paid.groupby(paid.issue_date.dt.to_period("M"))["total"].sum()
                 if len(paid) else pd.Series(dtype=float))
        exp_m = (exp.groupby(exp.date.dt.to_period("M"))["amount"].sum()
                 if len(exp) else pd.Series(dtype=float))
        flow = pd.DataFrame({
            "Month": [m.strftime("%b %y") for m in months],
            "Income": [float(inc_m.get(m, 0)) for m in months],
            "Expenses": [float(exp_m.get(m, 0)) for m in months],
        })
        fig = px.bar(flow.melt("Month", var_name="Type", value_name="Amount"),
                     x="Month", y="Amount", color="Type", barmode="group",
                     color_discrete_map={"Income": "#10B981", "Expenses": "#EF4444"})
        fig.update_layout(xaxis_title=None, yaxis_title=None, legend_title=None)
        chart(fig)
    with right:
        st.subheader("Expenses by category")
        if len(exp):
            by_cat = exp.groupby("category", as_index=False)["amount"].sum()
            fig = px.pie(by_cat, names="category", values="amount", hole=.55)
            fig.update_traces(textinfo="percent")
            chart(fig)
        else:
            st.info("No expenses yet.")

    left, right = st.columns(2)
    with left:
        st.subheader("Recent invoices")
        if len(inv):
            view = inv.head(6)[["number", "customer_name", "total", "status"]]
            st.dataframe(view, hide_index=True, width="stretch", column_config={
                "number": "Invoice", "customer_name": "Customer",
                "total": st.column_config.NumberColumn("Total", format=f"{CUR}%.2f"),
                "status": "Status"})
        else:
            st.info("No invoices yet.")
            st.page_link(PAGES["new_invoice"], label="Create your first invoice", icon="➕")
    with right:
        st.subheader("Overdue & due soon")
        if len(inv):
            soon = inv[(inv.status.isin(["Pending", "Overdue"])) &
                       (inv.due_date <= pd.Timestamp.today() + pd.Timedelta(days=7))]
            if len(soon):
                st.dataframe(soon[["number", "customer_name", "due_date", "total", "status"]],
                             hide_index=True, width="stretch", column_config={
                                 "number": "Invoice", "customer_name": "Customer",
                                 "due_date": st.column_config.DateColumn("Due"),
                                 "total": st.column_config.NumberColumn("Total", format=f"{CUR}%.2f"),
                                 "status": "Status"})
            else:
                st.success("Nothing due in the next 7 days. 🎉")
        else:
            st.info("Nothing to show yet.")


def page_customers():
    st.title("👥 Customers")
    customers = db.list_customers()

    with st.expander("➕ Add customer", expanded=not customers):
        with st.form("add_customer", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name *")
            email = c2.text_input("Email *")
            phone = c1.text_input("Phone")
            company = c2.text_input("Company")
            tax_id = c1.text_input("Tax ID / GSTIN")
            address = c2.text_area("Address", height=68)
            if st.form_submit_button("Save customer", type="primary"):
                if not name.strip() or not email.strip():
                    st.error("Name and email are required.")
                elif "@" not in email:
                    st.error("Please enter a valid email.")
                elif db.email_exists(email):
                    st.error("A customer with this email already exists.")
                else:
                    db.add_customer(dict(name=name.strip(), email=email.strip(), phone=phone.strip(),
                                         company=company.strip(), tax_id=tax_id.strip(),
                                         address=address.strip()))
                    st.toast(f"Customer {name} added", icon="✅")
                    st.rerun()

    if not customers:
        st.info("No customers yet — add one above.")
        return

    search = st.text_input("🔍 Search customers", placeholder="Name, email, company…")
    invoices = db.list_invoices()
    billed = {}
    for i in invoices:
        if i["status"] != "Cancelled":
            billed[i["customer_id"]] = billed.get(i["customer_id"], 0) + float(i["total"])
    df = pd.DataFrame(customers)
    df["billed"] = df["id"].map(billed).fillna(0)
    if search:
        mask = df[["name", "email", "company", "phone"]].fillna("").apply(
            lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
        df = df[mask]
    st.dataframe(df[["name", "email", "phone", "company", "billed"]], hide_index=True,
                 width="stretch", column_config={
                     "name": "Name", "email": "Email", "phone": "Phone", "company": "Company",
                     "billed": st.column_config.NumberColumn("Total billed", format=f"{CUR}%.2f")})

    st.subheader("Edit or delete")
    by_id = {c["id"]: c for c in customers}
    cid = st.selectbox("Customer", list(by_id), format_func=lambda k: f"{by_id[k]['name']} · {by_id[k]['email']}")
    c = by_id[cid]
    with st.form(f"edit_{cid}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", c["name"])
        email = c2.text_input("Email", c["email"])
        phone = c1.text_input("Phone", c.get("phone") or "")
        company = c2.text_input("Company", c.get("company") or "")
        tax_id = c1.text_input("Tax ID / GSTIN", c.get("tax_id") or "")
        address = c2.text_area("Address", c.get("address") or "", height=68)
        b1, b2 = st.columns(2)
        save = b1.form_submit_button("💾 Save changes", type="primary")
        remove = b2.form_submit_button("🗑️ Delete customer")
    if save:
        if not name.strip() or not email.strip():
            st.error("Name and email are required.")
        elif db.email_exists(email, exclude_id=cid):
            st.error("Another customer already uses this email.")
        else:
            db.update_customer(cid, dict(name=name.strip(), email=email.strip(), phone=phone.strip(),
                                         company=company.strip(), tax_id=tax_id.strip(),
                                         address=address.strip()))
            st.toast("Customer updated", icon="✅")
            st.rerun()
    if remove:
        db.delete_customer(cid)
        st.toast("Customer deleted", icon="🗑️")
        st.rerun()


def page_new_invoice():
    st.title("🧾 New invoice")
    customers = db.list_customers()
    if not customers:
        st.warning("Add a customer before creating an invoice.")
        st.page_link(PAGES["customers"], label="Go to Customers", icon="👥")
        return

    by_id = {c["id"]: c for c in customers}
    terms = int(SETTINGS.get("payment_terms_days") or 15)
    default_tax = float(SETTINGS.get("default_tax_rate") or 0)

    c1, c2, c3 = st.columns([2, 1, 1])
    cid = c1.selectbox("Customer", list(by_id), format_func=lambda k: by_id[k]["name"])
    issue = c2.date_input("Issue date", date.today())
    due = c3.date_input("Due date", issue + timedelta(days=terms), min_value=issue)

    st.markdown("**Line items** — click a cell to edit; add rows via the empty last row or ➕ in the table toolbar")
    if "items_seed" not in st.session_state:
        st.session_state.items_seed = 0
    items_df = st.data_editor(
        pd.DataFrame([{"description": "", "quantity": 1.0, "price": 0.0, "tax_rate": default_tax}]),
        key=f"items_{st.session_state.items_seed}",
        num_rows="dynamic", width="stretch", hide_index=True,
        column_config={
            "description": st.column_config.TextColumn("Description", required=True, width="large"),
            "quantity": st.column_config.NumberColumn("Qty", min_value=0.0, step=1.0, default=1.0),
            "price": st.column_config.NumberColumn(f"Unit price ({CUR})", min_value=0.0, format="%.2f", default=0.0),
            "tax_rate": st.column_config.NumberColumn("Tax %", min_value=0.0, max_value=100.0, default=default_tax),
        },
    )
    items = [
        {"description": str(r.description).strip(), "quantity": float(r.quantity or 0),
         "price": float(r.price or 0), "tax_rate": float(r.tax_rate or 0)}
        for r in items_df.itertuples()
        if isinstance(r.description, str) and r.description.strip()
    ]

    c1, c2 = st.columns([3, 1])
    notes = c1.text_area("Notes / payment instructions", height=90,
                         placeholder="e.g. Bank details, UPI ID, terms…")
    discount = c2.number_input(f"Discount ({CUR})", min_value=0.0, value=0.0, step=10.0)
    status = c2.selectbox("Status", ["Pending", "Draft", "Paid"])

    subtotal, tax, total = db.compute_totals(items, discount)
    t1, t2, t3 = st.columns(3)
    t1.metric("Subtotal", money(subtotal))
    t2.metric("Tax", money(tax))
    t3.metric("Total", money(total))

    if st.button("Create invoice", type="primary", disabled=not items):
        cust = by_id[cid]
        address = "\n".join(x for x in [cust.get("company"), cust.get("address")] if x)
        inv = db.add_invoice(dict(
            customer_id=cid, customer_name=cust["name"], customer_email=cust["email"],
            customer_address=address, issue_date=issue, due_date=due, status=status,
            items=items, discount=discount, notes=notes.strip(),
            paid_date=date.today() if status == "Paid" else None,
        ))
        st.session_state.items_seed += 1
        st.session_state.last_invoice = inv["id"]
        st.rerun()
    if not items:
        st.caption("Add at least one line item with a description to create the invoice.")

    last = st.session_state.get("last_invoice")
    if last and (inv := db.get_invoice(last)):
        st.success(f"Invoice **{inv['number']}** created for {inv['customer_name']} — {money(inv['total'])}")
        st.download_button("⬇️ Download PDF", generate_invoice_pdf(inv, SETTINGS),
                           file_name=f"{inv['number']}.pdf", mime="application/pdf")


def page_invoices():
    st.title("📋 Invoices")
    invoices = db.list_invoices()
    if not invoices:
        st.info("No invoices yet.")
        st.page_link(PAGES["new_invoice"], label="Create an invoice", icon="➕")
        return
    df = invoices_df(invoices)

    c1, c2, c3 = st.columns([2, 2, 1])
    search = c1.text_input("🔍 Search", placeholder="Invoice no. or customer")
    statuses = c2.multiselect("Status", ["Draft", "Pending", "Overdue", "Paid", "Cancelled"])
    period = c3.selectbox("Period", ["All time", "This month", "Last 30 days", "This year"])
    view = df
    if search:
        view = view[view.number.str.contains(search, case=False, regex=False)
                    | view.customer_name.fillna("").str.contains(search, case=False, regex=False)]
    if statuses:
        view = view[view.status.isin(statuses)]
    today = pd.Timestamp.today().normalize()
    if period == "This month":
        view = view[view.issue_date >= today.replace(day=1)]
    elif period == "Last 30 days":
        view = view[view.issue_date >= today - pd.Timedelta(days=30)]
    elif period == "This year":
        view = view[view.issue_date >= today.replace(month=1, day=1)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Invoices", len(view))
    m2.metric("Billed", money(view.loc[view.status != "Cancelled", "total"].sum()))
    m3.metric("Unpaid", money(view.loc[view.status.isin(["Pending", "Overdue"]), "total"].sum()))

    st.dataframe(view[["number", "customer_name", "issue_date", "due_date", "total", "status"]],
                 hide_index=True, width="stretch", column_config={
                     "number": "Invoice", "customer_name": "Customer",
                     "issue_date": st.column_config.DateColumn("Issued"),
                     "due_date": st.column_config.DateColumn("Due"),
                     "total": st.column_config.NumberColumn("Total", format=f"{CUR}%.2f"),
                     "status": "Status"})

    if view.empty:
        return
    st.subheader("Invoice details")
    by_id = {i["id"]: i for i in invoices}
    iid = st.selectbox("Select invoice", list(view.id),
                       format_func=lambda k: f"{by_id[k]['number']} · {by_id[k]['customer_name']} · {money(by_id[k]['total'])}")
    inv = by_id[iid]
    status = effective_status(inv)

    with st.container(border=True):
        h1, h2 = st.columns([3, 2])
        h1.markdown(f"### {inv['number']} &nbsp; {badge(status)}", unsafe_allow_html=True)
        h1.markdown(f"**{inv['customer_name']}** · {inv.get('customer_email') or ''}")
        h1.markdown(f"<span class='muted'>Issued {inv['issue_date']} · Due {inv['due_date']}"
                    + (f" · Paid {inv['paid_date']}" if inv.get("paid_date") else "") + "</span>",
                    unsafe_allow_html=True)
        h2.metric("Amount", money(inv["total"]))
        items = pd.DataFrame(inv.get("items") or [])
        if len(items):
            items["amount"] = items.quantity.astype(float) * items.price.astype(float)
            st.dataframe(items, hide_index=True, width="stretch", column_config={
                "description": "Description", "quantity": "Qty",
                "price": st.column_config.NumberColumn("Unit price", format=f"{CUR}%.2f"),
                "tax_rate": "Tax %",
                "amount": st.column_config.NumberColumn("Amount", format=f"{CUR}%.2f")})
        st.markdown(f"Subtotal **{money(inv['subtotal'])}** · Tax **{money(inv['tax'])}**"
                    + (f" · Discount **-{money(inv['discount'])}**" if inv.get("discount") else ""))
        if inv.get("notes"):
            st.caption(f"Notes: {inv['notes']}")

        b1, b2, b3, b4 = st.columns(4)
        b1.download_button("⬇️ PDF", generate_invoice_pdf(inv, SETTINGS), file_name=f"{inv['number']}.pdf",
                           mime="application/pdf", width="stretch")
        if inv["status"] in ("Pending", "Draft"):
            if b2.button("✅ Mark paid", type="primary", width="stretch"):
                db.set_invoice_status(iid, "Paid")
                st.toast(f"{inv['number']} marked as paid", icon="✅")
                st.rerun()
        elif inv["status"] == "Paid":
            if b2.button("↩️ Mark unpaid", width="stretch"):
                db.set_invoice_status(iid, "Pending")
                st.rerun()
        if inv["status"] != "Cancelled":
            if b3.button("🚫 Cancel", width="stretch"):
                db.set_invoice_status(iid, "Cancelled")
                st.rerun()
        else:
            if b3.button("♻️ Reopen", width="stretch"):
                db.set_invoice_status(iid, "Pending")
                st.rerun()
        if b4.button("📄 Duplicate", width="stretch"):
            terms = int(SETTINGS.get("payment_terms_days") or 15)
            new = db.add_invoice(dict(
                customer_id=inv["customer_id"], customer_name=inv["customer_name"],
                customer_email=inv["customer_email"], customer_address=inv.get("customer_address"),
                issue_date=date.today(), due_date=date.today() + timedelta(days=terms),
                status="Pending", items=inv["items"], discount=inv.get("discount") or 0,
                notes=inv.get("notes") or ""))
            st.toast(f"Created {new['number']}", icon="📄")
            st.rerun()

        with st.expander("✏️ Edit due date / notes, or delete"):
            with st.form(f"edit_inv_{iid}"):
                due = st.date_input("Due date", inv["due_date"] or date.today())
                notes = st.text_area("Notes", inv.get("notes") or "")
                e1, e2 = st.columns(2)
                save = e1.form_submit_button("Save", type="primary")
                confirm = e2.checkbox("Confirm delete")
                remove = e2.form_submit_button("🗑️ Delete invoice")
            if save:
                db.update_invoice(iid, {"due_date": due, "notes": notes})
                st.toast("Invoice updated", icon="💾")
                st.rerun()
            if remove:
                if confirm:
                    db.delete_invoice(iid)
                    st.toast("Invoice deleted", icon="🗑️")
                    st.rerun()
                else:
                    st.warning("Tick “Confirm delete” first.")


def page_expenses():
    st.title("💳 Expenses")

    with st.expander("➕ Add expense", expanded=True):
        with st.form("add_expense", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            exp_date = c1.date_input("Date", date.today())
            category = c2.selectbox("Category", db.EXPENSE_CATEGORIES)
            amount = c3.number_input(f"Amount ({CUR})", min_value=0.0, value=0.0, step=50.0)
            vendor = c1.text_input("Vendor / payee")
            method = c2.selectbox("Payment method", db.PAYMENT_METHODS)
            description = c3.text_input("Description")
            if st.form_submit_button("Add expense", type="primary"):
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    db.add_expense(dict(date=exp_date, category=category, vendor=vendor.strip(),
                                        description=description.strip(), amount=amount,
                                        payment_method=method))
                    st.toast("Expense added", icon="✅")
                    st.rerun()

    df = expenses_df(db.list_expenses())
    if df.empty:
        st.info("No expenses recorded yet.")
        return

    c1, c2, c3 = st.columns([2, 2, 2])
    cats = c1.multiselect("Category", sorted(df.category.dropna().unique()))
    min_d, max_d = df.date.min().date(), df.date.max().date()
    rng = c2.date_input("Date range", (min_d, max_d))
    search = c3.text_input("🔍 Search", placeholder="Vendor or description")
    view = df
    if cats:
        view = view[view.category.isin(cats)]
    if isinstance(rng, tuple) and len(rng) == 2:
        view = view[(view.date.dt.date >= rng[0]) & (view.date.dt.date <= rng[1])]
    if search:
        view = view[view.vendor.fillna("").str.contains(search, case=False, regex=False)
                    | view.description.fillna("").str.contains(search, case=False, regex=False)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Total", money(view.amount.sum()))
    m2.metric("Entries", len(view))
    m3.metric("Average", money(view.amount.mean() if len(view) else 0))

    st.caption("Edit cells directly, or select rows and press Delete, then **Save changes**.")
    edited = st.data_editor(
        view.assign(date=view.date.dt.date), key="exp_editor", hide_index=True,
        width="stretch", num_rows="dynamic", disabled=["id"],
        column_order=["date", "category", "vendor", "description", "payment_method", "amount"],
        column_config={
            "date": st.column_config.DateColumn("Date", required=True),
            "category": st.column_config.SelectboxColumn("Category", options=db.EXPENSE_CATEGORIES, required=True),
            "vendor": "Vendor", "description": "Description",
            "payment_method": st.column_config.SelectboxColumn("Method", options=db.PAYMENT_METHODS),
            "amount": st.column_config.NumberColumn(f"Amount ({CUR})", min_value=0.0, format="%.2f", required=True),
        },
    )
    if st.button("💾 Save changes", type="primary"):
        before = set(view.id)
        after = {r for r in edited.id if isinstance(r, str)}
        for eid in before - after:
            db.delete_expense(eid)
        for row in edited.to_dict("records"):
            data = dict(date=row["date"], category=row["category"], vendor=row.get("vendor") or "",
                        description=row.get("description") or "", amount=float(row["amount"] or 0),
                        payment_method=row.get("payment_method") or "")
            if isinstance(row.get("id"), str):
                db.update_expense(row["id"], data)
            elif data["amount"] > 0 and data["date"]:
                db.add_expense(data)
        st.toast("Expenses saved", icon="💾")
        st.rerun()


def page_reports():
    st.title("📈 Reports")
    inv = invoices_df(db.list_invoices())
    exp = expenses_df(db.list_expenses())

    today = date.today()
    c1, c2 = st.columns([1, 2])
    preset = c1.selectbox("Period", ["This year", "This month", "Last 3 months", "Last 12 months", "All time", "Custom"])
    starts = {
        "This year": today.replace(month=1, day=1),
        "This month": today.replace(day=1),
        "Last 3 months": today - timedelta(days=90),
        "Last 12 months": today - timedelta(days=365),
        "All time": date(2000, 1, 1),
    }
    if preset == "Custom":
        rng = c2.date_input("Date range", (today.replace(month=1, day=1), today))
        start, end = (rng if isinstance(rng, tuple) and len(rng) == 2 else (rng[0], rng[0]))
    else:
        start, end = starts[preset], today
        c2.markdown(f"<br><span class='muted'>{start:%d %b %Y} → {end:%d %b %Y}</span>", unsafe_allow_html=True)

    s, e = pd.Timestamp(start), pd.Timestamp(end)
    inv_p = inv[(inv.issue_date >= s) & (inv.issue_date <= e)] if len(inv) else inv
    exp_p = exp[(exp.date >= s) & (exp.date <= e)] if len(exp) else exp

    income = inv_p.loc[inv_p.status == "Paid", "total"].sum() if len(inv_p) else 0
    billed = inv_p.loc[inv_p.status != "Cancelled", "total"].sum() if len(inv_p) else 0
    tax = inv_p.loc[inv_p.status == "Paid", "tax"].sum() if len(inv_p) else 0
    spent = exp_p.amount.sum() if len(exp_p) else 0
    margin = ((income - spent) / income * 100) if income else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Billed", money(billed))
    m2.metric("Received", money(income))
    m3.metric("Expenses", money(spent))
    m4.metric("Net profit", money(income - spent), delta=f"{margin:.1f}% margin" if income else None)
    st.caption(f"Tax collected on paid invoices: **{money(tax)}**")

    tab1, tab2, tab3 = st.tabs(["Profit & loss", "Customers", "Expenses"])
    with tab1:
        paid = inv_p[inv_p.status == "Paid"] if len(inv_p) else inv_p
        inc_m = paid.groupby(paid.issue_date.dt.to_period("M"))["total"].sum() if len(paid) else pd.Series(dtype=float)
        exp_m = exp_p.groupby(exp_p.date.dt.to_period("M"))["amount"].sum() if len(exp_p) else pd.Series(dtype=float)
        months = sorted(set(inc_m.index) | set(exp_m.index))
        if months:
            pl = pd.DataFrame({"Month": [m.strftime("%b %Y") for m in months],
                               "Income": [float(inc_m.get(m, 0)) for m in months],
                               "Expenses": [float(exp_m.get(m, 0)) for m in months]})
            pl["Profit"] = pl.Income - pl.Expenses
            fig = px.line(pl, x="Month", y=["Income", "Expenses", "Profit"], markers=True,
                          color_discrete_map={"Income": "#10B981", "Expenses": "#EF4444", "Profit": "#4F46E5"})
            fig.update_layout(xaxis_title=None, yaxis_title=None, legend_title=None)
            chart(fig)
            st.dataframe(pl, hide_index=True, width="stretch", column_config={
                k: st.column_config.NumberColumn(k, format=f"{CUR}%.2f") for k in ("Income", "Expenses", "Profit")})
        else:
            st.info("No data in this period.")
    with tab2:
        valid = inv_p[inv_p.status != "Cancelled"] if len(inv_p) else inv_p
        if len(valid):
            top = (valid.groupby("customer_name")
                   .agg(invoices=("number", "count"), billed=("total", "sum"))
                   .reset_index().sort_values("billed", ascending=False))
            unpaid = valid[valid.status.isin(["Pending", "Overdue"])].groupby("customer_name")["total"].sum()
            top["outstanding"] = top.customer_name.map(unpaid).fillna(0)
            fig = px.bar(top.head(10), x="billed", y="customer_name", orientation="h", color_discrete_sequence=["#4F46E5"])
            fig.update_layout(yaxis=dict(autorange="reversed", title=None), xaxis_title=None)
            chart(fig, 300)
            st.dataframe(top, hide_index=True, width="stretch", column_config={
                "customer_name": "Customer", "invoices": "Invoices",
                "billed": st.column_config.NumberColumn("Billed", format=f"{CUR}%.2f"),
                "outstanding": st.column_config.NumberColumn("Outstanding", format=f"{CUR}%.2f")})
        else:
            st.info("No invoices in this period.")
    with tab3:
        if len(exp_p):
            by_cat = exp_p.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
            fig = px.bar(by_cat, x="category", y="amount", color_discrete_sequence=["#EF4444"])
            fig.update_layout(xaxis_title=None, yaxis_title=None)
            chart(fig, 300)
            by_cat["share"] = by_cat.amount / by_cat.amount.sum() * 100
            st.dataframe(by_cat, hide_index=True, width="stretch", column_config={
                "category": "Category",
                "amount": st.column_config.NumberColumn("Amount", format=f"{CUR}%.2f"),
                "share": st.column_config.ProgressColumn("Share", format="%.1f%%", min_value=0, max_value=100)})
        else:
            st.info("No expenses in this period.")

    st.subheader("Export")
    inv_out = inv_p.drop(columns=["items", "id", "customer_id", "created_at"], errors="ignore")
    exp_out = exp_p.drop(columns=["id"], errors="ignore")
    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇️ Invoices (CSV)", inv_out.to_csv(index=False), "invoices.csv", "text/csv",
                       width="stretch", disabled=inv_out.empty)
    d2.download_button("⬇️ Expenses (CSV)", exp_out.to_csv(index=False), "expenses.csv", "text/csv",
                       width="stretch", disabled=exp_out.empty)
    d3.download_button("⬇️ Full report (Excel)", to_excel({"Invoices": inv_out, "Expenses": exp_out}),
                       f"report_{start}_{end}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")


def page_settings():
    st.title("⚙️ Settings")
    tab1, tab2, tab3 = st.tabs(["Business profile", "Invoicing", "Data & storage"])
    with tab1:
        with st.form("biz"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Business name", SETTINGS["business_name"])
            email = c2.text_input("Email", SETTINGS["business_email"])
            phone = c1.text_input("Phone", SETTINGS["business_phone"])
            tax_id = c2.text_input("Tax ID / GSTIN", SETTINGS["business_tax_id"])
            address = st.text_area("Address", SETTINGS["business_address"])
            if st.form_submit_button("Save", type="primary"):
                db.save_settings(dict(business_name=name, business_email=email, business_phone=phone,
                                      business_tax_id=tax_id, business_address=address))
                st.toast("Business profile saved", icon="💾")
                st.rerun()
    with tab2:
        with st.form("inv_settings"):
            c1, c2 = st.columns(2)
            currency = c1.text_input("Currency symbol", SETTINGS["currency"], max_chars=4)
            tax_rate = c2.number_input("Default tax %", 0.0, 100.0, float(SETTINGS["default_tax_rate"] or 0))
            prefix = c1.text_input("Invoice number prefix", SETTINGS["invoice_prefix"])
            next_no = c2.number_input("Next invoice number", min_value=1, value=int(SETTINGS["next_invoice_number"]))
            terms = c1.number_input("Payment terms (days)", 0, 365, int(SETTINGS["payment_terms_days"] or 15))
            footer = c2.text_input("Invoice footer", SETTINGS["invoice_footer"])
            if st.form_submit_button("Save", type="primary"):
                db.save_settings(dict(currency=currency or "₹", default_tax_rate=tax_rate, invoice_prefix=prefix,
                                      next_invoice_number=int(next_no), payment_terms_days=int(terms),
                                      invoice_footer=footer))
                st.toast("Invoice settings saved", icon="💾")
                st.rerun()
    with tab3:
        backend = db.backend_name()
        st.markdown(f"**Current storage:** `{backend}`")
        if backend.startswith("SQLite"):
            st.warning(
                "Data is stored in a local SQLite file. On Railway (and most cloud hosts) the disk is "
                "wiped on every redeploy. To keep data permanently, add a **PostgreSQL** database and "
                "set the `DATABASE_URL` variable on this service — the app switches to it automatically."
            )
        else:
            st.success("Data is stored in PostgreSQL and persists across deploys.")
        st.markdown("**Sample data**")
        st.caption("Load a realistic online-store dataset (customers, orders as invoices, 12 months of "
                   "expenses). Fetched live from the free DummyJSON API, with an offline fallback.")
        s1, s2 = st.columns(2)
        if s1.button("📦 Load sample data", width="stretch"):
            with st.spinner("Fetching sample dataset…"):
                counts, source = db.load_sample_data()
            st.success(f"Loaded {counts['customers']} customers, {counts['invoices']} invoices and "
                       f"{counts['expenses']} expenses from {source}.")
        if db.has_sample_data() and s2.button("🧹 Remove sample data", width="stretch"):
            db.remove_sample_data()
            st.toast("Sample data removed", icon="🧹")
            st.rerun()
        st.divider()
        st.markdown("**Import real Amazon orders (Seller Central)**")
        st.caption("Amazon has no public API for customer data. If you sell on Amazon, download your "
                   "order report from Seller Central → Reports → Fulfillment / Order Reports "
                   "(\"All Orders\", .txt or .csv) and upload it here. Each order becomes an invoice.")
        amz = st.file_uploader("Amazon order report", type=["txt", "tsv", "csv"], key="amz")
        if amz and st.button("Import Amazon orders", type="primary"):
            from sample_data import parse_amazon_orders
            try:
                payload = parse_amazon_orders(amz.getvalue(), float(SETTINGS["default_tax_rate"] or 0),
                                              int(SETTINGS["payment_terms_days"] or 0))
                counts = db.import_all(payload)
                st.success(f"Imported {counts['customers']} customers and {counts['invoices']} orders "
                           "(already-imported orders are skipped).")
            except ValueError as exc:
                st.error(str(exc))
        st.divider()
        st.download_button("⬇️ Download full backup (JSON)", db.export_all(),
                           f"finance_backup_{date.today()}.json", "application/json")
        st.markdown("**Restore / migrate from a backup**")
        up = st.file_uploader("Backup file (.json)", type=["json"])
        replace = st.checkbox("Replace all existing data (otherwise merge)")
        if up and st.button("Import backup", type="primary"):
            try:
                counts = db.import_all(json.load(up), replace=replace)
                if "settings" in (payload := json.loads(up.getvalue())):
                    db.save_settings(payload["settings"])
                st.success(f"Imported {counts['customers']} customers, {counts['invoices']} invoices, "
                           f"{counts['expenses']} expenses.")
            except (ValueError, KeyError) as exc:
                st.error(f"Invalid backup file: {exc}")


# ------------------------------------------------------------------ navigation

PAGES = {
    "dashboard": st.Page(page_dashboard, title="Dashboard", icon="📊", url_path="dashboard", default=True),
    "new_invoice": st.Page(page_new_invoice, title="New invoice", icon="➕", url_path="new-invoice"),
    "invoices": st.Page(page_invoices, title="Invoices", icon="📋", url_path="invoices"),
    "customers": st.Page(page_customers, title="Customers", icon="👥", url_path="customers"),
    "expenses": st.Page(page_expenses, title="Expenses", icon="💳", url_path="expenses"),
    "reports": st.Page(page_reports, title="Reports", icon="📈", url_path="reports"),
    "settings": st.Page(page_settings, title="Settings", icon="⚙️", url_path="settings"),
}

nav = st.navigation({
    "Overview": [PAGES["dashboard"], PAGES["reports"]],
    "Sales": [PAGES["new_invoice"], PAGES["invoices"], PAGES["customers"]],
    "Spending": [PAGES["expenses"]],
    "Admin": [PAGES["settings"]],
})

with st.sidebar:
    st.markdown(f"### 💰 {SETTINGS['business_name']}")
    st.caption("Automated Invoicing & Expense Tracker")
    st.caption(f"Storage: {db.backend_name()}")
    if os.environ.get("APP_PASSWORD") and st.button("Sign out", width="stretch"):
        st.session_state.authenticated = False
        st.rerun()

nav.run()
