from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from invoice_agent.schema import (
    GoodsReceipt,
    Invoice,
    LineItem,
    POLine,
    PurchaseOrder,
    ReceiptLine,
)

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"

D = Decimal


@pytest.fixture(scope="session")
def dataset() -> Path:
    return DATASET


def truth(stem: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATASET / "ground_truth" / f"{stem}.json").read_text())
    return data


@pytest.fixture
def po() -> PurchaseOrder:
    return PurchaseOrder(
        po_number="PO-1",
        vendor="Acme Widget Works Ltd",
        currency="USD",
        lines=[
            POLine(
                line_no=1,
                sku="W-100",
                description="Blue widget, large",
                quantity=D(10),
                unit_price=D("5.00"),
            ),
            POLine(
                line_no=2,
                sku="W-200",
                description="Red gadget, small",
                quantity=D(4),
                unit_price=D("20.00"),
            ),
        ],
    )


@pytest.fixture
def receipt() -> GoodsReceipt:
    return GoodsReceipt(
        receipt_id="GR-1",
        po_number="PO-1",
        lines=[ReceiptLine(line_no=1, quantity=D(10)), ReceiptLine(line_no=2, quantity=D(4))],
    )


def make_invoice(
    lines: list[tuple[str, str | None, int, str]],
    *,
    number: str = "INV-1",
    po_number: str | None = "PO-1",
    vendor: str = "Acme Widget Works Limited",
    currency: str = "USD",
    tax_rate: str = "0",
    date: str = "2026-03-02",
) -> Invoice:
    items = [
        LineItem(
            description=desc,
            sku=sku,
            quantity=D(qty),
            unit_price=D(price),
            amount=(D(qty) * D(price)).quantize(D("0.01")),
        )
        for desc, sku, qty, price in lines
    ]
    subtotal = sum((li.amount for li in items), D(0))
    tax = (subtotal * D(tax_rate)).quantize(D("0.01"))
    return Invoice(
        vendor=vendor,
        invoice_number=number,
        invoice_date=date,  # type: ignore[arg-type]
        po_number=po_number,
        currency=currency,
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=subtotal + tax,
    )
