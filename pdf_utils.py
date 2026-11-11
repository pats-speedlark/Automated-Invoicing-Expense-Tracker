"""Invoice PDF generation with ReportLab."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = colors.HexColor("#4F46E5")
MUTED = colors.HexColor("#6B7280")


def _money(value: float, currency: str) -> str:
    # ReportLab's built-in fonts don't contain "₹", so use "Rs." in the PDF.
    symbol = "Rs. " if currency == "₹" else currency
    return f"{symbol}{float(value):,.2f}"


def _esc(text) -> str:
    return (str(text or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def generate_invoice_pdf(invoice: dict, settings: dict) -> bytes:
    currency = settings.get("currency", "₹")
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title=f"Invoice {invoice['number']}",
    )
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=styles["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=normal, fontSize=8.5, textColor=MUTED)
    right = ParagraphStyle("r", parent=normal, alignment=TA_RIGHT)
    h_business = ParagraphStyle("b", parent=normal, fontSize=16, leading=20, fontName="Helvetica-Bold")
    h_invoice = ParagraphStyle("i", parent=right, fontSize=22, leading=26, fontName="Helvetica-Bold", textColor=ACCENT)

    story = []

    biz_lines = [settings.get("business_address"), settings.get("business_email"), settings.get("business_phone")]
    if settings.get("business_tax_id"):
        biz_lines.append(f"Tax ID / GSTIN: {settings['business_tax_id']}")
    biz = [Paragraph(_esc(settings.get("business_name", "")), h_business)]
    biz += [Paragraph(_esc(l), small) for l in biz_lines if l]

    meta = [
        Paragraph("INVOICE", h_invoice),
        Paragraph(f"<b>No:</b> {_esc(invoice['number'])}", right),
        Paragraph(f"<b>Date:</b> {invoice.get('issue_date') or ''}", right),
        Paragraph(f"<b>Due:</b> {invoice.get('due_date') or ''}", right),
        Paragraph(f"<b>Status:</b> {_esc(invoice.get('status'))}", right),
    ]
    header = Table([[biz, meta]], colWidths=[doc.width * 0.6, doc.width * 0.4])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [header, Spacer(1, 8 * mm)]

    bill = [Paragraph("<b>BILL TO</b>", small), Paragraph(f"<b>{_esc(invoice.get('customer_name'))}</b>", normal)]
    for line in (invoice.get("customer_address"), invoice.get("customer_email")):
        if line:
            bill.append(Paragraph(_esc(line), normal))
    story += bill + [Spacer(1, 6 * mm)]

    rows = [["#", "Description", "Qty", "Unit price", "Tax %", "Amount"]]
    for n, item in enumerate(invoice.get("items") or [], start=1):
        qty, price = float(item["quantity"]), float(item["price"])
        rows.append([
            str(n), Paragraph(_esc(item.get("description")), normal), f"{qty:g}",
            _money(price, currency), f"{float(item.get('tax_rate', 0)):g}", _money(qty * price, currency),
        ])
    items_tbl = Table(rows, colWidths=[8 * mm, None, 16 * mm, 28 * mm, 16 * mm, 30 * mm], repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items_tbl, Spacer(1, 4 * mm)]

    totals = [["Subtotal", _money(invoice.get("subtotal", 0), currency)],
              ["Tax", _money(invoice.get("tax", 0), currency)]]
    if float(invoice.get("discount") or 0):
        totals.append(["Discount", "- " + _money(invoice["discount"], currency)])
    totals.append(["TOTAL", _money(invoice.get("total", 0), currency)])
    tot_tbl = Table(totals, colWidths=[35 * mm, 35 * mm], hAlign="RIGHT")
    tot_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("TEXTCOLOR", (0, -1), (-1, -1), ACCENT),
        ("LINEABOVE", (0, -1), (-1, -1), 1, ACCENT),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]))
    story += [tot_tbl, Spacer(1, 8 * mm)]

    if invoice.get("notes"):
        story += [Paragraph("<b>Notes</b>", small), Paragraph(_esc(invoice["notes"]), normal), Spacer(1, 6 * mm)]
    if settings.get("invoice_footer"):
        story.append(Paragraph(_esc(settings["invoice_footer"]), small))

    doc.build(story)
    return buffer.getvalue()
