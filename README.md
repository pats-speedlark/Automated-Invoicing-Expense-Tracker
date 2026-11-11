# 💰 Automated Invoicing & Expense Tracker

A Streamlit app for small businesses and freelancers: customers, multi-line invoices with PDF export, expense tracking, profit & loss reports, and backups. Works on laptops, tablets and phones.

## Features

- **Dashboard**: income, expenses, outstanding/overdue amounts, a 12-month cash-flow chart, expenses by category, and invoices that are due soon
- **Invoices**: multiple line items with per-line tax, discounts, notes, due dates, and automatic numbering (`INV-1001`, …). Statuses are Draft, Pending, Paid and Cancelled, and Pending invoices past their due date show as **Overdue**. You can mark invoices paid or unpaid, duplicate, edit or delete them, and download a PDF
- **Customers**: add, edit, delete and search, with company and GSTIN fields and total billed per customer
- **Expenses**: vendor, category and payment method, with filters (category, date range, search) and inline editing in a spreadsheet-style grid
- **Reports**: preset or custom periods, monthly P&L, top customers, category breakdown, and CSV or Excel export
- **Settings**: business profile (shown on PDFs), currency, default tax, invoice prefix and numbering, payment terms, and a JSON backup you can restore
- **Sample data**: one click loads a realistic online-store dataset (customers, orders as invoices, 12 months of expenses) live from the free [DummyJSON](https://dummyjson.com) API. If the API can't be reached, an offline generator is used instead. Sample data can be removed again with one click
- **Amazon Seller Central import**: upload your real *All Orders* report (`.txt`/`.csv`) and each Amazon order becomes an invoice
- **Optional password**: set `APP_PASSWORD` and the app asks for it before opening
- **Storage**: PostgreSQL when `DATABASE_URL` is set, otherwise a local SQLite file. Data from the old `data/*.json` and `expenses.csv` files is migrated automatically

> **About Amazon data:** Amazon has no public API that returns customer data. The Selling Partner API only returns *your own* seller account's orders, and it needs a registered developer app and OAuth credentials. That is why the app imports the Seller Central order report instead, and uses DummyJSON for demo data.

## Run locally

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

To use PostgreSQL locally, set `DATABASE_URL=postgresql://user:pass@localhost:5432/dbname` before starting the app.

## Deploy on Railway

1. Create a new project from this GitHub repo. `railway.json` sets the start command and the `/_stcore/health` health check, and `Procfile` is a fallback.
2. **Add PostgreSQL**: in the project, choose *New → Database → PostgreSQL*.
3. On the app service, open *Variables* and add `DATABASE_URL = ${{Postgres.DATABASE_URL}}`. Optionally add `APP_PASSWORD`.
4. On the app service, open *Settings → Networking* and click **Generate Domain**.

Without `DATABASE_URL` the app still runs on SQLite, but Railway wipes the disk on every redeploy. Use Postgres, or attach a volume and set `DATA_DIR` to its mount path.

### Why the earlier deploy didn't launch

The repo had no start command, so Railway didn't know how to run Streamlit. Streamlit also has to listen on Railway's `$PORT` on `0.0.0.0`. `railway.json` and `Procfile` now run:

```
python start.py   # = streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
```

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI (pages, navigation, responsive CSS) |
| `db.py` | SQLAlchemy storage layer (PostgreSQL / SQLite), backup and restore |
| `pdf_utils.py` | Invoice PDF generation (ReportLab) |
| `sample_data.py` | DummyJSON sample dataset and the Amazon order-report importer |
| `railway.json`, `Procfile`, `.python-version` | Deployment config |
