"""Build the synthetic evaluation dataset: PDFs, ground truth, POs and receipts.

Run ``invoice-agent generate-dataset OUT_DIR``. Output is deterministic.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..normalize import quantize
from ..schema import (
    Decision,
    GoodsReceipt,
    Invoice,
    LineItem,
    POLine,
    PurchaseOrder,
    ReceiptLine,
)
from .catalog import VENDORS, Item, Vendor
from .render import RenderSpec, rasterize, render_bytes

D = Decimal
ZERO = D("0")
#: (catalog index, quantity) or (catalog index, quantity, invoiced unit price)
LineSpec = tuple[int, int] | tuple[int, int, Decimal]
BASE_DATE = dt.date(2026, 3, 2)


@dataclass
class Case:
    case_id: str
    vendor: str
    description: str
    decision: Decision
    reasons: list[str]
    po_number: str | None
    invoice: Invoice
    spec: RenderSpec
    scanned: bool = False


@dataclass
class Builder:
    rng: random.Random = field(default_factory=lambda: random.Random(20260302))
    pos: dict[str, PurchaseOrder] = field(default_factory=dict)
    receipts: list[GoodsReceipt] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)
    _po_seq: int = 100
    _inv_seq: dict[str, int] = field(default_factory=dict)
    _rcpt_seq: int = 0

    # -- purchase orders -------------------------------------------------
    def po(
        self,
        vendor_key: str,
        lines: list[tuple[int, int]],
        received: str | list[dict[int, int]] = "full",
    ) -> str:
        """Create a PO. ``received`` is "full", "none", or receipts as {line_no: qty}."""
        v = VENDORS[vendor_key]
        self._po_seq += 1
        number = f"PO-2026-{self._po_seq:04d}"
        po_lines = [
            POLine(
                line_no=i,
                sku=v.items[idx].sku,
                description=v.items[idx].po_desc,
                quantity=D(qty),
                unit_price=v.items[idx].price,
            )
            for i, (idx, qty) in enumerate(lines, start=1)
        ]
        self.pos[number] = PurchaseOrder(
            po_number=number,
            vendor=v.po_name,
            currency=v.currency,
            lines=po_lines,
            receipt_required=v.receipt_required,
        )
        if v.receipt_required and received != "none":
            batches = (
                [{pl.line_no: int(pl.quantity) for pl in po_lines}]
                if received == "full"
                else received
            )
            assert isinstance(batches, list)
            for batch in batches:
                self._rcpt_seq += 1
                self.receipts.append(
                    GoodsReceipt(
                        receipt_id=f"GR-{self._rcpt_seq:05d}",
                        po_number=number,
                        date=BASE_DATE - dt.timedelta(days=3),
                        lines=[ReceiptLine(line_no=k, quantity=D(q)) for k, q in batch.items()],
                    )
                )
        return number

    def po_lines(self, po_number: str) -> list[tuple[int, int]]:
        """(catalog index, qty) pairs of a PO, for invoicing it in full."""
        po = self.pos[po_number]
        v = next(v for v in VENDORS.values() if v.po_name == po.vendor)
        skus = [it.sku for it in v.items]
        return [(skus.index(pl.sku or ""), int(pl.quantity)) for pl in po.lines]

    # -- invoices ---------------------------------------------------------
    def next_number(self, v: Vendor) -> str:
        n = self._inv_seq.get(v.key, 0) + 1
        self._inv_seq[v.key] = n
        if v.key == "brightforge":
            return f"BF-2026/{400 + n:04d}"
        if v.key == "quillfeather":
            return f"QOS-{10400 + n}"
        if v.key == "kettleby":
            return f"KLC-INV-{870 + n:05d}"
        if v.key == "pinecone":
            return f"PCS-2026-{30 + n:04d}"
        return f"HFP {778100 + n}"

    def invoice(
        self,
        case_id: str,
        vendor_key: str,
        po_number: str | None,
        lines: Sequence[LineSpec],
        *,
        description: str,
        decision: Decision,
        reasons: list[str] | None = None,
        expected_po: str | None = "same",
        print_po: bool = True,
        number: str | None = None,
        date: dt.date | None = None,
        discount_pct: Decimal = ZERO,
        extra_lines: list[LineItem] | None = None,
        mutate: Callable[[dict[str, Any]], None] | None = None,
        currency: str | None = None,
        scanned: bool = False,
    ) -> Invoice:
        v = VENDORS[vendor_key]
        items: list[LineItem] = []
        units: list[str] = []
        for entry in lines:
            idx, qty = entry[0], entry[1]
            item: Item = v.items[idx]
            price = entry[2] if len(entry) == 3 else item.price
            items.append(
                LineItem(
                    description=item.invoice_desc,
                    sku=item.sku if "sku" in v.style.columns else None,
                    quantity=D(qty),
                    unit_price=price,
                    amount=quantize(price * qty),
                )
            )
            units.append(item.unit)
        for extra in extra_lines or []:
            items.append(extra)
            units.append("ea")
        gross = sum((li.amount for li in items), D("0"))
        discount = quantize(gross * discount_pct)
        tax = quantize((gross - discount) * v.tax_rate)
        issued = date or (BASE_DATE + dt.timedelta(days=len(self.cases)))
        data: dict[str, Any] = {
            "vendor": v.invoice_name,
            "invoice_number": number or self.next_number(v),
            "invoice_date": issued,
            "due_date": issued + dt.timedelta(days=v.terms_days),
            "po_number": po_number if print_po else None,
            "currency": currency or v.currency,
            "line_items": items,
            "subtotal": gross,
            "discount": discount,
            "tax": tax,
            "total": gross - discount + tax,
        }
        if mutate:
            mutate(data)
        inv = Invoice(**data)
        discount_label = None
        if discount:
            discount_label = f"Less: loyalty discount ({int(discount_pct * 100)}%)"
        spec = RenderSpec(
            vendor=v, invoice=inv, units=units, discount_label=discount_label, currency=currency
        )
        self.cases.append(
            Case(
                case_id=case_id,
                vendor=vendor_key,
                description=description,
                decision=decision,
                reasons=sorted(reasons or []),
                po_number=po_number if expected_po == "same" else expected_po,
                invoice=inv,
                spec=spec,
                scanned=scanned,
            )
        )
        return inv


def build() -> Builder:
    b = Builder()
    rnd = b.rng
    ok = Decision.AUTO_APPROVE
    review = Decision.NEEDS_REVIEW
    reject = Decision.REJECT

    # ---- purchase orders ------------------------------------------------
    q1 = b.po("quillfeather", [(0, 20), (1, 5), (3, 10)])
    q2 = b.po("quillfeather", [(2, 4), (4, 30), (5, 12)])
    q3 = b.po("quillfeather", [(6, 10), (7, 10)], [{1: 4, 2: 10}, {1: 2}])
    q4 = b.po("quillfeather", [(0, 50), (5, 8)], [{1: 30, 2: 8}])
    q5 = b.po("quillfeather", [(1, 6), (4, 40)])
    q6 = b.po("quillfeather", [(0, 15), (2, 3)])
    q9 = b.po("quillfeather", [(3, 25), (6, 6), (7, 2)])
    q10 = b.po("quillfeather", [(0, 10), (1, 2)])
    q11 = b.po("quillfeather", [(4, 12), (5, 6), (6, 4), (2, 1)])
    q12 = b.po("quillfeather", [(7, 5)])

    b1 = b.po("brightforge", [(0, 40), (2, 10), (4, 12)])
    b2 = b.po("brightforge", [(1, 6), (3, 2)])
    b3 = b.po("brightforge", [(5, 20), (0, 100)])
    b4 = b.po("brightforge", [(3, 4), (4, 10)])
    b5 = b.po("brightforge", [(2, 20)])
    b7 = b.po("brightforge", [(1, 4), (5, 3)])
    b8 = b.po("brightforge", [(0, 24), (1, 2), (2, 5), (3, 1), (4, 6), (5, 2)])
    b9 = b.po("brightforge", [(4, 30)])
    b10 = b.po("brightforge", [(2, 8), (5, 8)])

    k1 = b.po("kettleby", [(0, 10), (2, 4)])
    k2 = b.po("kettleby", [(1, 3), (4, 2), (3, 10)])
    k3 = b.po("kettleby", [(5, 6), (0, 5)])
    k4 = b.po("kettleby", [(2, 6), (3, 5)])
    k5 = b.po("kettleby", [(4, 5), (1, 2)], [{1: 3, 2: 2}])
    k8 = b.po("kettleby", [(5, 2), (3, 4)])
    k9 = b.po("kettleby", [(0, 20), (1, 1), (2, 2), (3, 3), (4, 1)])

    p1 = b.po("pinecone", [(0, 24), (1, 40)])
    p2 = b.po("pinecone", [(2, 30), (3, 20)])
    p3 = b.po("pinecone", [(0, 16)])
    p4 = b.po("pinecone", [(1, 60)])
    p5 = b.po("pinecone", [(3, 12), (2, 8)])
    p6 = b.po("pinecone", [(0, 10), (3, 5)])
    p7 = b.po("pinecone", [(2, 12)])
    p8 = b.po("pinecone", [(1, 10), (0, 4)])

    def hlines(indices: range | list[int]) -> list[tuple[int, int]]:
        return [(i, rnd.randint(1, 24)) for i in indices]

    h1 = b.po("harborline", hlines(range(0, 30)))
    h2 = b.po("harborline", hlines(range(2, 47)))
    h3 = b.po("harborline", hlines([4, 9, 17, 22, 40]))
    h4 = b.po("harborline", hlines(range(10, 38)))
    h5_lines = hlines(range(20, 46))
    h5_receipt = {i: q for i, (_, q) in enumerate(h5_lines, start=1)}
    h5_short = {1: 1, 4: 2, 9: 1, 15: 3, 22: 1}
    for line_no, short in h5_short.items():
        h5_receipt[line_no] = max(1, h5_receipt[line_no] - short)
    h5 = b.po("harborline", h5_lines, [h5_receipt])
    h6 = b.po("harborline", hlines([1, 5, 12, 33, 34, 47]), "none")
    h7 = b.po("harborline", hlines(range(8, 16)))
    h8 = b.po("harborline", hlines([3, 27, 31, 44]))
    h9 = b.po("harborline", hlines(range(35, 47)))
    h10 = b.po("harborline", hlines([0, 16, 32]))

    # ---- invoices, in submission order ------------------------------------
    first = b.invoice(
        "q01", "quillfeather", q1, b.po_lines(q1), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "q02", "quillfeather", q2, b.po_lines(q2), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "q03",
        "quillfeather",
        q3,
        [(6, 6), (7, 10)],
        description="Partial receipt across two receipts, invoiced quantity equals received",
        decision=ok,
    )
    b.invoice(
        "q04",
        "quillfeather",
        q4,
        [(0, 50), (5, 8)],
        description="Billed for 50 units, only 30 received",
        decision=review,
        reasons=["QTY_EXCEEDS_RECEIVED"],
    )
    b.invoice(
        "q05",
        "quillfeather",
        q5,
        b.po_lines(q5),
        print_po=False,
        expected_po=q5,
        description="No PO number printed; PO must be inferred",
        decision=review,
        reasons=["PO_MISSING"],
    )

    def cent_off(d: dict[str, Any]) -> None:
        li = d["line_items"][0]
        d["line_items"][0] = li.model_copy(update={"amount": li.amount + D("0.01")})
        d["subtotal"] += D("0.01")
        d["total"] += D("0.01")

    b.invoice(
        "q06",
        "quillfeather",
        q6,
        b.po_lines(q6),
        mutate=cent_off,
        description="One line amount is off by one cent (rounding)",
        decision=ok,
    )
    b.invoice(
        "q07",
        "quillfeather",
        q1,
        b.po_lines(q1),
        number=first.invoice_number,
        date=first.invoice_date,
        description="Exact duplicate submission of q01",
        decision=reject,
        reasons=["DUPLICATE_INVOICE"],
    )
    b.invoice(
        "q08",
        "quillfeather",
        h10,
        [(0, 3), (4, 2)],
        description="Invoice cites a PO issued to a different vendor",
        decision=reject,
        reasons=["VENDOR_MISMATCH"],
    )
    b.invoice(
        "q09", "quillfeather", q9, b.po_lines(q9), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "q10",
        "quillfeather",
        q10,
        b.po_lines(q10),
        scanned=True,
        expected_po=None,
        description="Scanned image with no text layer",
        decision=review,
        reasons=["NO_TEXT_LAYER"],
    )
    b.invoice(
        "q11", "quillfeather", q11, b.po_lines(q11), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "q12", "quillfeather", q12, b.po_lines(q12), description="Clean single line", decision=ok
    )

    bf1 = b.invoice(
        "b01",
        "brightforge",
        b1,
        b.po_lines(b1),
        description="Clean 3-way match, European number format",
        decision=ok,
    )
    b.invoice(
        "b02", "brightforge", b2, b.po_lines(b2), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "b03",
        "brightforge",
        b3,
        [(5, 20, D("15.45")), (0, 100)],
        description="Unit price 1% above PO, inside tolerance",
        decision=ok,
    )
    b.invoice(
        "b04",
        "brightforge",
        b4,
        [(3, 4, D("61.56")), (4, 10)],
        description="Unit price 8% above PO",
        decision=review,
        reasons=["PRICE_VARIANCE"],
    )
    b.invoice(
        "b05",
        "brightforge",
        b5,
        [(2, 25)],
        description="Billed 25 units against a PO for 20",
        decision=reject,
        reasons=["QTY_EXCEEDS_ORDERED"],
    )
    b.invoice(
        "b06",
        "brightforge",
        b1,
        b.po_lines(b1),
        number=(bf1.invoice_number or "").replace("/", "-").replace("BF-", "BF "),
        description="Duplicate of b01 with the invoice number reformatted",
        decision=reject,
        reasons=["DUPLICATE_INVOICE"],
    )
    b.invoice(
        "b07",
        "brightforge",
        b7,
        b.po_lines(b7),
        currency="USD",
        description="Billed in USD against a EUR purchase order",
        decision=review,
        reasons=["CURRENCY_MISMATCH"],
    )
    b.invoice(
        "b08", "brightforge", b8, b.po_lines(b8), description="Clean six-line invoice", decision=ok
    )
    b.invoice(
        "b09", "brightforge", b9, b.po_lines(b9), description="Clean single line", decision=ok
    )
    b.invoice(
        "b10", "brightforge", b10, b.po_lines(b10), description="Clean 3-way match", decision=ok
    )

    kf1 = b.invoice(
        "k01", "kettleby", k1, b.po_lines(k1), description="Clean 3-way match", decision=ok
    )
    b.invoice(
        "k02",
        "kettleby",
        k2,
        b.po_lines(k2),
        description="Long descriptions wrap onto two lines",
        decision=ok,
    )
    surcharge = LineItem(
        description="Hazardous goods handling surcharge",
        sku="KLC-SUR1",
        quantity=D(1),
        unit_price=D("15.00"),
        amount=D("15.00"),
    )
    b.invoice(
        "k03",
        "kettleby",
        k3,
        b.po_lines(k3),
        extra_lines=[surcharge],
        description="Adds a surcharge line that is not on the PO",
        decision=review,
        reasons=["LINE_NOT_ON_PO"],
    )

    def total_wrong(d: dict[str, Any]) -> None:
        d["total"] += D("10.00")

    b.invoice(
        "k04",
        "kettleby",
        k4,
        b.po_lines(k4),
        mutate=total_wrong,
        description="Printed total is 10.00 higher than subtotal plus VAT",
        decision=review,
        reasons=["TOTAL_MISMATCH"],
    )
    b.invoice(
        "k05",
        "kettleby",
        k5,
        [(4, 3), (1, 2)],
        description="Partial receipt, invoiced quantity equals received",
        decision=ok,
    )
    b.invoice(
        "k06",
        "kettleby",
        "PO-2026-0999",
        [(0, 2)],
        expected_po=None,
        description="Cites a PO number that does not exist",
        decision=review,
        reasons=["PO_NOT_FOUND"],
    )
    b.invoice(
        "k07",
        "kettleby",
        k1,
        b.po_lines(k1),
        date=kf1.invoice_date,
        description="Resubmission of k01 under a new invoice number",
        decision=reject,
        reasons=["POSSIBLE_DUPLICATE", "QTY_EXCEEDS_ORDERED"],
    )
    b.invoice("k08", "kettleby", k8, b.po_lines(k8), description="Clean 3-way match", decision=ok)
    b.invoice(
        "k09", "kettleby", k9, b.po_lines(k9), description="Clean five-line invoice", decision=ok
    )

    b.invoice(
        "p01",
        "pinecone",
        p1,
        b.po_lines(p1),
        description="Clean 2-way match (services)",
        decision=ok,
    )
    b.invoice(
        "p02",
        "pinecone",
        p2,
        b.po_lines(p2),
        discount_pct=D("0.05"),
        description="5% invoice-level discount",
        decision=ok,
    )
    b.invoice(
        "p03",
        "pinecone",
        p3,
        [(0, 20)],
        description="20 hours billed against 16 ordered",
        decision=reject,
        reasons=["QTY_EXCEEDS_ORDERED"],
    )
    b.invoice(
        "p04a",
        "pinecone",
        p4,
        [(1, 40)],
        description="First partial invoice, 40 of 60 hours",
        decision=ok,
    )
    b.invoice(
        "p04b",
        "pinecone",
        p4,
        [(1, 30)],
        description="Second invoice pushes the PO to 70 of 60 hours",
        decision=reject,
        reasons=["QTY_EXCEEDS_ORDERED"],
    )

    def subtotal_wrong(d: dict[str, Any]) -> None:
        d["subtotal"] += D("25.00")
        d["total"] += D("25.00")

    b.invoice(
        "p05",
        "pinecone",
        p5,
        b.po_lines(p5),
        discount_pct=D("0.05"),
        mutate=subtotal_wrong,
        description="Printed subtotal is 25.00 more than the line amounts",
        decision=review,
        reasons=["SUBTOTAL_MISMATCH"],
    )
    b.invoice(
        "p06",
        "pinecone",
        p6,
        b.po_lines(p6),
        print_po=False,
        expected_po=p6,
        description="No PO number printed; PO must be inferred",
        decision=review,
        reasons=["PO_MISSING"],
    )
    b.invoice(
        "p07",
        "pinecone",
        p7,
        [(2, 12, D("200.00"))],
        description="Rate below PO price",
        decision=ok,
    )
    b.invoice("p08", "pinecone", p8, b.po_lines(p8), description="Clean 2-way match", decision=ok)

    b.invoice(
        "h01",
        "harborline",
        h1,
        b.po_lines(h1),
        description="Two-page invoice, 30 lines",
        decision=ok,
    )
    b.invoice(
        "h02",
        "harborline",
        h2,
        b.po_lines(h2),
        description="Two-page invoice, 45 lines",
        decision=ok,
    )
    b.invoice("h03", "harborline", h3, b.po_lines(h3), description="Clean 3-way match", decision=ok)
    h4_lines: list[tuple[int, int, Decimal]] = []
    for n, (idx, qty) in enumerate(b.po_lines(h4)):
        price = VENDORS["harborline"].items[idx].price
        h4_lines.append((idx, qty, quantize(price * D("1.15")) if n == 16 else price))
    b.invoice(
        "h04",
        "harborline",
        h4,
        h4_lines,
        description="Two pages; one unit price 15% above PO",
        decision=review,
        reasons=["PRICE_VARIANCE"],
    )
    h5_inv = [(idx, h5_receipt[n]) for n, (idx, _) in enumerate(b.po_lines(h5), start=1)]
    b.invoice(
        "h05",
        "harborline",
        h5,
        h5_inv,
        description="Five lines short-received; invoice bills only what arrived",
        decision=ok,
    )
    b.invoice(
        "h06",
        "harborline",
        h6,
        b.po_lines(h6),
        description="Goods invoiced before any receipt was posted",
        decision=review,
        reasons=["QTY_EXCEEDS_RECEIVED"],
    )
    b.invoice("h07", "harborline", h7, b.po_lines(h7), description="Clean 3-way match", decision=ok)
    b.invoice(
        "h08",
        "harborline",
        h8,
        b.po_lines(h8),
        print_po=False,
        expected_po=h8,
        description="No PO number printed; PO must be inferred",
        decision=review,
        reasons=["PO_MISSING"],
    )
    b.invoice("h09", "harborline", h9, b.po_lines(h9), description="Clean 3-way match", decision=ok)
    b.invoice(
        "h10", "harborline", h10, b.po_lines(h10), description="Clean 3-way match", decision=ok
    )
    return b


def write_dataset(out: Path) -> dict[str, int]:
    """Write the dataset to ``out`` and return counts."""
    b = build()
    (out / "invoices").mkdir(parents=True, exist_ok=True)
    (out / "ground_truth").mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, case in enumerate(b.cases, start=1):
        stem = f"{n:03d}_{case.case_id}"
        pdf = render_bytes(case.spec)
        if case.scanned:
            pdf = rasterize(pdf)
        (out / "invoices" / f"{stem}.pdf").write_bytes(pdf)
        truth = {
            "file": f"invoices/{stem}.pdf",
            "case": case.case_id,
            "vendor_layout": case.vendor,
            "description": case.description,
            "invoice": case.invoice.model_dump(mode="json"),
            "expected": {
                "decision": case.decision.value,
                "po_number": case.po_number,
                "reason_codes": case.reasons,
            },
        }
        (out / "ground_truth" / f"{stem}.json").write_text(json.dumps(truth, indent=2) + "\n")
        manifest.append(
            {
                "file": truth["file"],
                "case": case.case_id,
                "expected_decision": case.decision.value,
                "description": case.description,
            }
        )
    _dump(out / "purchase_orders.json", [po.model_dump(mode="json") for po in b.pos.values()])
    _dump(out / "receipts.json", [r.model_dump(mode="json") for r in b.receipts])
    _dump(out / "manifest.json", manifest)
    return {"invoices": len(b.cases), "purchase_orders": len(b.pos), "receipts": len(b.receipts)}


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")
