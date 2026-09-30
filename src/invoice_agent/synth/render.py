"""Render synthetic invoices to PDF with reportlab.

Output is byte-for-byte reproducible (``invariant=1``), so the dataset can be
regenerated and diffed.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen.canvas import Canvas

from ..schema import Invoice
from .catalog import BUYER, FOOTER, Vendor

PAGE_W, PAGE_H = A4
LEFT, RIGHT = 50.0, PAGE_W - 50.0


@dataclass
class RenderSpec:
    """What to draw. ``invoice`` holds the printed values, errors included."""

    vendor: Vendor
    invoice: Invoice
    units: list[str] = field(default_factory=list)
    discount_label: str | None = None
    currency: str | None = None


_COL_X: dict[str, dict[str, float]] = {
    # right edge for numbers, left edge for text
    "desc,qty,price,amount": {"desc": LEFT, "qty": 360, "price": 450, "amount": RIGHT},
    "pos,sku,desc,qty,price,amount": {
        "pos": LEFT,
        "sku": 75,
        "desc": 130,
        "qty": 400,
        "price": 470,
        "amount": RIGHT,
    },
    "sku,desc,qty,unit,price,amount": {
        "sku": LEFT,
        "desc": 110,
        "qty": 340,
        "unit": 350,
        "price": 460,
        "amount": RIGHT,
    },
    "sku,desc,qty,price,amount": {
        "sku": LEFT,
        "desc": 115,
        "qty": 370,
        "price": 455,
        "amount": RIGHT,
    },
}
_NUMERIC = {"qty", "price", "amount", "pos"}


def _fmt_qty(q: Decimal) -> str:
    return f"{q:f}".rstrip("0").rstrip(".") if "." in f"{q:f}" else f"{q:f}"


def render(spec: RenderSpec, path: Path) -> None:
    buf = render_bytes(spec)
    path.write_bytes(buf)


def render_bytes(spec: RenderSpec) -> bytes:
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4, invariant=1)
    c.setTitle(f"Invoice {spec.invoice.invoice_number}")
    c.setAuthor("invoice-agent synthetic data")
    _Painter(c, spec).paint()
    c.save()
    return buf.getvalue()


class _Painter:
    def __init__(self, c: Canvas, spec: RenderSpec) -> None:
        self.c = c
        self.spec = spec
        self.v = spec.vendor
        self.s = spec.vendor.style
        self.cur = spec.currency or spec.invoice.currency or spec.vendor.currency
        self.cols = _COL_X[",".join(self.s.columns)]

    def money(self, value: Decimal | None, in_table: bool = False) -> str:
        return self.s.fmt_money(value if value is not None else Decimal("0"), self.cur, in_table)

    def paint(self) -> None:
        rows = self._rows()
        pages: list[list[tuple[str, ...]]] = []
        capacity = self.s.rows_first_page
        current: list[tuple[str, ...]] = []
        for row in rows:
            if sum(len(r) - 6 for r in current) + len(row) - 6 > capacity:
                pages.append(current)
                current = []
                capacity = self.s.rows_next_page
            current.append(row)
        pages.append(current)
        total_pages = len(pages)
        for i, page_rows in enumerate(pages):
            if i == 0:
                y = self._header()
            else:
                y = PAGE_H - 70
                self.c.setFont(self.s.bold, 10)
                self.c.drawString(
                    LEFT,
                    y + 20,
                    f"{self.v.invoice_name}  {self.s.labels['number']} "
                    f"{self.spec.invoice.invoice_number} (continued)",
                )
            y = self._table(page_rows, y)
            if i == total_pages - 1:
                self._totals(y - 10)
            else:
                self.c.setFont(self.s.font, 8)
                self.c.drawString(LEFT, 70, "Continued on next page")
            self._footer(i + 1, total_pages)
            self.c.showPage()

    def _header(self) -> float:
        c, s, v, inv = self.c, self.s, self.v, self.spec.invoice
        top = PAGE_H - 55
        if s.header == "vendor_left":
            c.setFont(s.bold, 16)
            c.drawString(LEFT, top, v.invoice_name)
            c.setFont(s.bold, 20)
            c.drawRightString(RIGHT, top, s.title)
            y = top - 16
        elif s.header == "title_first":
            c.setFont(s.bold, 18)
            c.drawString(LEFT, top, s.title)
            c.setFont(s.bold, 13)
            c.drawString(LEFT, top - 24, v.invoice_name)
            y = top - 40
        else:
            c.setFont(s.bold, 16)
            c.drawCentredString(PAGE_W / 2, top, v.invoice_name)
            c.setFont(s.font, 9)
            c.drawCentredString(PAGE_W / 2, top - 14, ", ".join(v.address))
            c.setFont(s.bold, 14)
            c.drawCentredString(PAGE_W / 2, top - 36, s.title)
            y = top - 52
        c.setFont(s.font, 9)
        if s.header != "centered":
            for line in v.address:
                c.drawString(LEFT, y, line)
                y -= 12
        meta_y = y - 14
        meta = [
            (s.labels["number"], inv.invoice_number or ""),
            (s.labels["date"], s.fmt_date(inv.invoice_date) if inv.invoice_date else ""),
            (s.labels["due"], s.fmt_date(inv.due_date) if inv.due_date else ""),
        ]
        if inv.po_number:
            meta.append((s.labels["po"], inv.po_number))
        if s.currency_note:
            meta.append((s.currency_note.format(cur=self.cur), ""))
        c.setFont(s.font, 10)
        yy = meta_y
        for label, value in meta:
            c.drawString(330, yy, label)
            c.drawRightString(RIGHT, yy, value)
            yy -= 14
        c.setFont(s.bold, 10)
        by = meta_y
        c.drawString(LEFT, by, "Bill to:")
        c.setFont(s.font, 10)
        for line in BUYER:
            by -= 14
            c.drawString(LEFT, by, line)
        return float(min(yy, by)) - 30

    def _rows(self) -> list[tuple[str, ...]]:
        rows = []
        for n, li in enumerate(self.spec.invoice.line_items, start=1):
            unit = self.spec.units[n - 1] if self.spec.units else "ea"
            cells = {
                "pos": str(n),
                "sku": li.sku or "",
                "qty": _fmt_qty(li.quantity),
                "unit": unit,
                "price": self.money(li.unit_price, in_table=True),
                "amount": self.money(li.amount, in_table=True),
            }
            desc_lines = [li.description]
            if self.s.wrap_desc:
                desc_lines = simpleSplit(li.description, self.s.font, 9, self.s.wrap_desc)
            ordered = tuple(cells.get(col, "") for col in ("pos", "sku", "qty", "unit", "price"))
            rows.append((*ordered, cells["amount"], *desc_lines))
        return rows

    def _table(self, rows: list[tuple[str, ...]], y: float) -> float:
        c, s = self.c, self.s
        c.setFont(s.bold, 9)
        for col in s.columns:
            x = self.cols[col]
            title = s.column_titles[col]
            if col in _NUMERIC and col != "pos":
                c.drawRightString(x, y, title)
            else:
                c.drawString(x, y, title)
        c.line(LEFT, y - 4, RIGHT, y - 4)
        y -= 18
        c.setFont(s.font, 9)
        for row in rows:
            pos, sku, qty, unit, price, amount, *desc = row
            values = {
                "pos": pos,
                "sku": sku,
                "qty": qty,
                "unit": unit,
                "price": price,
                "amount": amount,
            }
            for col in s.columns:
                if col == "desc":
                    c.drawString(self.cols[col], y, desc[0])
                elif col in _NUMERIC and col != "pos":
                    c.drawRightString(self.cols[col], y, values[col])
                else:
                    c.drawString(self.cols[col], y, values[col])
            for extra in desc[1:]:
                y -= 11
                c.drawString(self.cols["desc"], y, extra)
            y -= 15
        c.line(LEFT, y + 6, RIGHT, y + 6)
        return y

    def _totals(self, y: float) -> None:
        c, s, inv = self.c, self.s, self.spec.invoice
        lines: list[tuple[str, str]] = [(s.totals["subtotal"], self.money(inv.subtotal))]
        if inv.discount:
            label = self.spec.discount_label or s.totals.get("discount", "Discount")
            lines.append((label, self.money(-inv.discount)))
        lines.append((self.v.tax_label, self.money(inv.tax)))
        lines.append((s.totals["total"], self.money(inv.total)))
        for i, (label, value) in enumerate(lines):
            bold = i == len(lines) - 1
            c.setFont(s.bold if bold else s.font, 11 if bold else 10)
            c.drawString(330, y, label)
            c.drawRightString(RIGHT, y, value)
            y -= 16
        c.setFont(s.font, 8)
        c.drawString(LEFT, y - 10, f"Payment terms: net {self.v.terms_days} days.")

    def _footer(self, page: int, total: int) -> None:
        self.c.setFont("Helvetica-Oblique", 7)
        self.c.drawString(LEFT, 40, FOOTER)
        self.c.drawRightString(RIGHT, 40, f"Page {page} of {total}")


def rasterize(pdf: bytes, dpi: int = 110) -> bytes:
    """Return a copy of ``pdf`` where every page is a flat image (no text layer).

    This imitates a scanned invoice.
    """
    import pypdfium2 as pdfium

    src = pdfium.PdfDocument(pdf)
    out = io.BytesIO()
    c = Canvas(out, pagesize=A4, invariant=1)
    for page in src:
        image = page.render(scale=dpi / 72).to_pil().convert("L")
        png = io.BytesIO()
        image.save(png, format="PNG", optimize=True)
        png.seek(0)
        c.drawImage(ImageReader(png), 0, 0, width=PAGE_W, height=PAGE_H)
        c.showPage()
    c.save()
    return out.getvalue()
