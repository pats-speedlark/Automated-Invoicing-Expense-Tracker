import streamlit as st
import pandas as pd
import json
import csv
import os
import uuid
from datetime import date
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------------- CONFIGURATION ----------------

st.set_page_config(
    page_title="Automated Invoicing & Expense Tracker",
    page_icon="💰",
    layout="wide"
)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

CUSTOMERS_FILE = os.path.join(DATA_DIR, "customers.json")
INVOICES_FILE = os.path.join(DATA_DIR, "invoices.json")
EXPENSES_FILE = os.path.join(DATA_DIR, "expenses.csv")


# ---------------- FILE HANDLING ----------------

def load_json(filename):
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_expenses():
    if not os.path.exists(EXPENSES_FILE):
        return []
    with open(EXPENSES_FILE, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_expenses(expenses):
    fields = ["id", "date", "category", "description", "amount"]
    with open(EXPENSES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(expenses)


customers = load_json(CUSTOMERS_FILE)
invoices = load_json(INVOICES_FILE)
expenses = load_expenses()


# ---------------- PDF GENERATION ----------------

def generate_invoice_pdf(invoice):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawString(50, height - 60, "INVOICE")

    pdf.setFont("Helvetica", 11)
    y = height - 110

    details = [
        f"Invoice Number: {invoice['id']}",
        f"Date: {invoice['date']}",
        f"Customer: {invoice['customer']}",
        f"Email: {invoice['email']}",
        f"Description: {invoice['description']}",
        f"Quantity: {invoice['quantity']}",
        f"Unit Price: Rs. {invoice['price']:.2f}",
        f"Subtotal: Rs. {invoice['subtotal']:.2f}",
        f"Tax ({invoice['tax_rate']}%): Rs. {invoice['tax']:.2f}",
    ]

    for detail in details:
        pdf.drawString(50, y, detail)
        y -= 25

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(50, y - 10, f"TOTAL: Rs. {invoice['total']:.2f}")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 60, "Thank you for your business!")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# ---------------- SIDEBAR ----------------

st.sidebar.title("💰 Finance Manager")
st.sidebar.caption("Automated Invoicing & Expense Tracker")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Customers",
        "Create Invoice",
        "Invoices",
        "Expense Tracker",
        "Reports"
    ]
)

st.sidebar.divider()
st.sidebar.caption("BCA 7th Semester Minor Project")
st.sidebar.caption("Python Application Development")


# ---------------- DASHBOARD ----------------

if page == "Dashboard":

    st.title("📊 Financial Dashboard")
    st.write("Welcome to your financial management system!")

    total_income = sum(
        float(i["total"]) for i in invoices
        if i["status"] == "Paid"
    )

    total_expenses = sum(float(e["amount"]) for e in expenses)

    pending = sum(
        float(i["total"]) for i in invoices
        if i["status"] == "Pending"
    )

    balance = total_income - total_expenses

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Total Income", f"₹{total_income:,.2f}")
    c2.metric("Total Expenses", f"₹{total_expenses:,.2f}")
    c3.metric("Pending Invoices", f"₹{pending:,.2f}")
    c4.metric("Net Balance", f"₹{balance:,.2f}")

    st.divider()
    st.subheader("Income vs Expenses")

    chart = pd.DataFrame({
        "Category": ["Income", "Expenses"],
        "Amount": [total_income, total_expenses]
    })

    st.bar_chart(chart.set_index("Category"))

    st.subheader("Recent Invoices")

    if invoices:
        st.dataframe(
            pd.DataFrame(invoices).tail(5),
            use_container_width=True
        )
    else:
        st.info("No invoices available yet.")


# ---------------- CUSTOMERS ----------------

elif page == "Customers":

    st.title("👥 Customer Management")

    with st.form("customer_form"):
        name = st.text_input("Customer Name")
        email = st.text_input("Email Address")
        phone = st.text_input("Phone Number")
        address = st.text_area("Address")

        submitted = st.form_submit_button("Add Customer")

        if submitted:
            if not name.strip() or not email.strip():
                st.error("Name and email are required.")

            elif any(
                c["email"].lower() == email.strip().lower()
                for c in customers
            ):
                st.error("This email is already registered.")

            else:
                customers.append({
                    "id": str(uuid.uuid4())[:8],
                    "name": name.strip(),
                    "email": email.strip(),
                    "phone": phone.strip(),
                    "address": address.strip()
                })

                save_json(CUSTOMERS_FILE, customers)
                st.success("Customer added successfully!")
                st.rerun()

    st.divider()
    st.subheader("Customer Records")

    if customers:
        st.dataframe(pd.DataFrame(customers), use_container_width=True)

        selected = st.selectbox(
            "Select customer to delete",
            range(len(customers)),
            format_func=lambda i: customers[i]["name"]
        )

        if st.button("Delete Selected Customer"):
            customers.pop(selected)
            save_json(CUSTOMERS_FILE, customers)
            st.success("Customer deleted.")
            st.rerun()
    else:
        st.info("No customers registered.")


# ---------------- CREATE INVOICE ----------------

elif page == "Create Invoice":

    st.title("🧾 Create New Invoice")

    if not customers:
        st.warning("Please add a customer before creating an invoice.")

    else:
        with st.form("invoice_form"):

            customer_names = [c["name"] for c in customers]

            selected_customer = st.selectbox(
                "Select Customer",
                customer_names
            )

            description = st.text_input("Product / Service Description")

            quantity = st.number_input(
                "Quantity", min_value=1, value=1
            )

            price = st.number_input(
                "Price per unit (₹)",
                min_value=0.0,
                value=100.0
            )

            tax_rate = st.number_input(
                "Tax Percentage",
                min_value=0.0,
                max_value=100.0,
                value=18.0
            )

            invoice_date = st.date_input(
                "Invoice Date", value=date.today()
            )

            submitted = st.form_submit_button("Generate Invoice")

            if submitted:

                if not description.strip():
                    st.error("Please enter a description.")

                else:
                    customer = next(
                        c for c in customers
                        if c["name"] == selected_customer
                    )

                    subtotal = quantity * price
                    tax = subtotal * tax_rate / 100
                    total = subtotal + tax

                    invoice = {
                        "id": "INV-" + uuid.uuid4().hex[:8].upper(),
                        "date": str(invoice_date),
                        "customer": customer["name"],
                        "email": customer["email"],
                        "description": description.strip(),
                        "quantity": quantity,
                        "price": price,
                        "tax_rate": tax_rate,
                        "subtotal": subtotal,
                        "tax": tax,
                        "total": total,
                        "status": "Pending"
                    }

                    invoices.append(invoice)
                    save_json(INVOICES_FILE, invoices)

                    st.success("Invoice generated successfully!")

                    st.write("Invoice Number:", invoice["id"])
                    st.write("Total Amount:", f"₹{total:,.2f}")

                    pdf_data = generate_invoice_pdf(invoice)


# ---------------- INVOICES ----------------

elif page == "Invoices":

    st.title("📋 Invoice Management")

    if invoices:

        st.dataframe(
            pd.DataFrame(invoices),
            use_container_width=True
        )

        invoice_ids = [i["id"] for i in invoices]

        selected_id = st.selectbox("Select Invoice", invoice_ids)

        selected_invoice = next(
            i for i in invoices if i["id"] == selected_id
        )

        st.write(
            "Total Amount:",
            f"₹{float(selected_invoice['total']):,.2f}"
        )

        col1, col2 = st.columns(2)

        with col1:
            if selected_invoice["status"] == "Pending":
                if st.button("Mark as Paid"):
                    selected_invoice["status"] = "Paid"
                    save_json(INVOICES_FILE, invoices)
                    st.success("Payment status updated.")
                    st.rerun()
            else:
                st.success("This invoice is already paid.")

        with col2:
            pdf_data = generate_invoice_pdf(selected_invoice)

            st.download_button(
                "Download PDF",
                data=pdf_data,
                file_name=selected_id + ".pdf",
                mime="application/pdf"
            )

    else:
        st.info("No invoices created yet.")


# ---------------- EXPENSE TRACKER ----------------

elif page == "Expense Tracker":

    st.title("💳 Expense Tracker")

    with st.form("expense_form"):

        expense_date = st.date_input("Expense Date", value=date.today())

        category = st.selectbox(
            "Category",
            [
                "Food",
                "Travel",
                "Rent",
                "Shopping",
                "Utilities",
                "Salary",
                "Other"
            ]
        )

        description = st.text_input("Expense Description")

        amount = st.number_input(
            "Amount (₹)", min_value=0.01, value=100.0
        )

        submitted = st.form_submit_button("Add Expense")

        if submitted:

            expenses.append({
                "id": str(uuid.uuid4())[:8],
                "date": str(expense_date),
                "category": category,
                "description": description,
                "amount": str(amount)
            })

            save_expenses(expenses)
            st.success("Expense added successfully!")
            st.rerun()

    st.divider()
    st.subheader("Expense Records")

    if expenses:

        expense_df = pd.DataFrame(expenses)

        st.dataframe(expense_df, use_container_width=True)

        st.metric(
            "Total Expenses",
            f"₹{sum(float(e['amount']) for e in expenses):,.2f}"
        )

        selected_expense = st.selectbox(
            "Select expense to delete",
            range(len(expenses)),
            format_func=lambda i: expenses[i]["description"]
        )

        if st.button("Delete Selected Expense"):
            expenses.pop(selected_expense)
            save_expenses(expenses)
            st.success("Expense deleted.")
            st.rerun()

    else:
        st.info("No expenses recorded yet.")


# ---------------- REPORTS ----------------

elif page == "Reports":

    st.title("📈 Financial Reports")

    total_income = sum(
        float(i["total"]) for i in invoices
        if i["status"] == "Paid"
    )

    total_expenses = sum(float(e["amount"]) for e in expenses)

    pending = sum(
        float(i["total"]) for i in invoices
        if i["status"] == "Pending"
    )

    st.metric("Total Income", f"₹{total_income:,.2f}")
    st.metric("Total Expenses", f"₹{total_expenses:,.2f}")
    st.metric("Pending Payments", f"₹{pending:,.2f}")
    st.metric("Net Balance", f"₹{total_income - total_expenses:,.2f}")

    st.divider()

    if invoices:
        invoice_csv = pd.DataFrame(invoices).to_csv(index=False)
        st.download_button(
            "Download Invoice Report (CSV)",
            data=invoice_csv,
            file_name="invoice_report.csv",
            mime="text/csv"
        )

    if expenses:
        expense_csv = pd.DataFrame(expenses).to_csv(index=False)
        st.download_button(
            "Download Expense Report (CSV)",
            data=expense_csv,
            file_name="expense_report.csv",
            mime="text/csv"
        )

    if not invoices and not expenses:
        st.info("Add invoices or expenses to generate reports.")

st.sidebar.success("Application is running!")
