"""Fictional vendors, their catalogs and their invoice styles.

Every company, address and product here is invented for testing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class Item:
    sku: str
    invoice_desc: str
    po_desc: str
    price: Decimal
    unit: str = "ea"


@dataclass(frozen=True)
class Style:
    title: str
    header: str  # "vendor_left" | "title_first" | "centered"
    labels: dict[str, str]
    columns: tuple[str, ...]  # subset of pos, sku, desc, qty, unit, price, amount
    column_titles: dict[str, str]
    totals: dict[str, str]
    fmt_date: Callable[[dt.date], str]
    fmt_money: Callable[[Decimal, str, bool], str]  # (value, currency, in_table)
    font: str = "Helvetica"
    bold: str = "Helvetica-Bold"
    wrap_desc: float | None = None  # points; wrap long descriptions
    rows_first_page: int = 26
    rows_next_page: int = 34
    currency_note: str | None = None  # template with {cur}


@dataclass(frozen=True)
class Vendor:
    key: str
    invoice_name: str
    po_name: str
    address: tuple[str, str]
    currency: str
    tax_rate: Decimal
    tax_label: str
    style: Style
    items: tuple[Item, ...]
    inv_prefix: str
    receipt_required: bool = True
    terms_days: int = 30
    extra: dict[str, str] = field(default_factory=dict)


def _group(value: Decimal, thousands: str, decimal: str) -> str:
    s = f"{abs(value):,.2f}"
    s = s.replace(",", "\x00").replace(".", decimal).replace("\x00", thousands)
    return ("-" if value < 0 else "") + s


def us_money(symbol: bool) -> Callable[[Decimal, str, bool], str]:
    def fmt(v: Decimal, cur: str, in_table: bool) -> str:
        body = _group(v, ",", ".")
        if in_table and not symbol:
            return body
        sign = "-" if body.startswith("-") else ""
        return f"{sign}${body.lstrip('-')}"

    return fmt


def eu_money(v: Decimal, cur: str, in_table: bool) -> str:
    body = _group(v, ".", ",")
    if in_table:
        return body
    return f"{body} €" if cur == "EUR" else f"{body} {cur}"


def gbp_money(v: Decimal, cur: str, in_table: bool) -> str:
    body = _group(v, ",", ".")
    sign = "-" if body.startswith("-") else ""
    return f"{sign}£{body.lstrip('-')}"


def code_money(v: Decimal, cur: str, in_table: bool) -> str:
    body = _group(v, ",", ".")
    return body if in_table else f"{cur} {body}"


def plain_money(v: Decimal, cur: str, in_table: bool) -> str:
    return _group(v, ",", ".")


QUILLFEATHER = Vendor(
    key="quillfeather",
    invoice_name="Quillfeather Office Supply Co.",
    po_name="Quillfeather Office Supply Company",
    address=("41 Inkwell Lane", "Papertown, ZZ 00001"),
    currency="USD",
    tax_rate=D("0.0825"),
    tax_label="Sales Tax (8.25%)",
    inv_prefix="QOS-",
    style=Style(
        title="INVOICE",
        header="vendor_left",
        labels={
            "number": "Invoice No:",
            "date": "Invoice Date:",
            "due": "Due Date:",
            "po": "PO Number:",
        },
        columns=("desc", "qty", "price", "amount"),
        column_titles={
            "desc": "Description",
            "qty": "Qty",
            "price": "Unit Price",
            "amount": "Amount",
        },
        totals={"subtotal": "Subtotal", "total": "Total Due"},
        fmt_date=lambda d: d.strftime("%m/%d/%Y"),
        fmt_money=us_money(symbol=True),
    ),
    items=(
        Item(
            "QOS-1001",
            "Copy paper A4 80gsm, ream of 500",
            "A4 copy paper 80gsm 500 sheets",
            D("6.49"),
        ),
        Item(
            "QOS-1002", "Ballpoint pens, blue, box of 50", "Blue ballpoint pen box/50", D("11.90")
        ),
        Item(
            "QOS-1003", "Stapler, heavy duty, 100-sheet", "Heavy duty stapler 100 sheet", D("34.75")
        ),
        Item("QOS-1004", "Staples 26/6, box of 5000", "Staples 26/6 (5000)", D("3.20")),
        Item("QOS-1005", "Lever arch file, A4, black", "A4 lever arch file black", D("4.15")),
        Item("QOS-1006", "Sticky notes 76x76mm, 12 pads", "Sticky notes 76x76 12-pack", D("8.60")),
        Item(
            "QOS-1007",
            "Whiteboard markers, assorted, 4-pack",
            "Whiteboard marker 4pk assorted",
            D("5.95"),
        ),
        Item(
            "QOS-1008",
            "Desk organiser, mesh, 5 compartments",
            "Mesh desk organizer 5 compartment",
            D("18.40"),
        ),
    ),
)

BRIGHTFORGE = Vendor(
    key="brightforge",
    invoice_name="Brightforge Maschinenteile GmbH",
    po_name="Brightforge Maschinenteile",
    address=("Beispielstrasse 12", "99999 Musterstadt"),
    currency="EUR",
    tax_rate=D("0.19"),
    tax_label="MwSt. 19% / VAT",
    inv_prefix="BF-",
    style=Style(
        title="RECHNUNG / INVOICE",
        header="title_first",
        labels={
            "number": "Rechnungsnr. / Invoice No.:",
            "date": "Datum / Date:",
            "due": "Fällig / Due:",
            "po": "Bestellnr. / PO:",
        },
        columns=("pos", "sku", "desc", "qty", "price", "amount"),
        column_titles={
            "pos": "Pos",
            "sku": "Art.-Nr.",
            "desc": "Beschreibung / Description",
            "qty": "Menge",
            "price": "Einzelpreis",
            "amount": "Betrag",
        },
        totals={"subtotal": "Zwischensumme / Subtotal", "total": "Gesamtbetrag / Total"},
        fmt_date=lambda d: d.strftime("%d.%m.%Y"),
        fmt_money=eu_money,
        currency_note="Währung / Currency: {cur}",
    ),
    items=(
        Item(
            "BF-40110",
            "Kugellager 6204-2RS / Ball bearing 6204-2RS",
            "Ball bearing 6204-2RS",
            D("4.85"),
        ),
        Item(
            "BF-40220",
            "Hydraulikschlauch DN10 1m / Hydraulic hose DN10",
            "Hydraulic hose DN10, 1 m",
            D("23.40"),
        ),
        Item(
            "BF-40330",
            "Sechskantschraube M8x40 / Hex bolt M8x40 (100)",
            "Hex bolt M8x40 pack of 100",
            D("12.10"),
        ),
        Item(
            "BF-40440", "Zahnriemen HTD 8M / Timing belt HTD 8M", "Timing belt HTD-8M", D("57.00")
        ),
        Item(
            "BF-40550",
            "Druckluftkupplung / Pneumatic coupler 1/4in",
            "Pneumatic quick coupler 1/4in",
            D("9.75"),
        ),
        Item(
            "BF-40660",
            "Industriefett 1kg / Industrial grease 1kg",
            "Industrial grease 1 kg tin",
            D("15.30"),
        ),
    ),
)

KETTLEBY = Vendor(
    key="kettleby",
    invoice_name="Kettleby Lab Consumables Ltd",
    po_name="Kettleby Laboratory Consumables Limited",
    address=("Unit 7, Fictional Science Park", "Testford TF0 0ZZ"),
    currency="GBP",
    tax_rate=D("0.20"),
    tax_label="VAT @ 20%",
    inv_prefix="KLC-INV-",
    style=Style(
        title="TAX INVOICE",
        header="centered",
        labels={
            "number": "Invoice #",
            "date": "Date of issue",
            "due": "Payment due",
            "po": "Your order ref",
        },
        columns=("sku", "desc", "qty", "unit", "price", "amount"),
        column_titles={
            "sku": "Item",
            "desc": "Description",
            "qty": "Qty",
            "unit": "Unit",
            "price": "Price",
            "amount": "Line total",
        },
        totals={"subtotal": "Net", "total": "Amount due"},
        fmt_date=lambda d: d.strftime("%d %b %Y"),
        fmt_money=gbp_money,
        wrap_desc=190.0,
    ),
    items=(
        Item(
            "KLC-2201",
            "Nitrile examination gloves, powder-free, size M, box of 100",
            "Nitrile gloves M (100)",
            D("7.45"),
            "box",
        ),
        Item(
            "KLC-2202",
            "Serological pipettes, 10 mL, sterile, individually wrapped, case of 200",
            "Serological pipette 10ml sterile x200",
            D("48.90"),
            "case",
        ),
        Item(
            "KLC-2203",
            "Microcentrifuge tubes 1.5 mL, natural, bag of 500",
            "Microtube 1.5ml natural (500)",
            D("12.25"),
            "bag",
        ),
        Item(
            "KLC-2204",
            "Petri dishes 90 mm, vented, sleeve of 20",
            "Petri dish 90mm vented x20",
            D("6.80"),
            "sleeve",
        ),
        Item(
            "KLC-2205",
            "Pipette tips 200 uL, racked, pack of 960",
            "Pipette tips 200ul racked 960",
            D("39.50"),
            "pack",
        ),
        Item("KLC-2206", "Lab coat, polycotton, size L", "Lab coat polycotton L", D("21.00"), "ea"),
    ),
)

PINECONE = Vendor(
    key="pinecone",
    invoice_name="Pinecone Cloud Services Inc.",
    po_name="Pinecone Cloud Services, Inc",
    address=("900 Imaginary Ave, Suite 4", "Nowhere City, ZZ 00002"),
    currency="USD",
    tax_rate=D("0"),
    tax_label="Tax",
    inv_prefix="PCS-2026-",
    receipt_required=False,
    style=Style(
        title="Invoice",
        header="vendor_left",
        labels={
            "number": "Invoice number",
            "date": "Issued",
            "due": "Due",
            "po": "Purchase order",
        },
        columns=("desc", "qty", "price", "amount"),
        column_titles={"desc": "Service", "qty": "Hours", "price": "Rate", "amount": "Amount"},
        totals={
            "subtotal": "Subtotal",
            "total": "Total (USD)",
            "discount": "Less: loyalty discount",
        },
        fmt_date=lambda d: d.strftime("%B %d, %Y"),
        fmt_money=code_money,
    ),
    items=(
        Item(
            "PCS-SVC-01",
            "Cloud architecture consulting",
            "Cloud architecture consulting (hours)",
            D("185.00"),
            "hr",
        ),
        Item(
            "PCS-SVC-02",
            "Managed Kubernetes support",
            "Managed Kubernetes support hrs",
            D("140.00"),
            "hr",
        ),
        Item(
            "PCS-SVC-03",
            "Security review and hardening",
            "Security hardening review",
            D("210.00"),
            "hr",
        ),
        Item(
            "PCS-SVC-04",
            "On-call incident response",
            "Incident response on-call",
            D("160.00"),
            "hr",
        ),
    ),
)

_PARTS = [
    "Brake pad set, front",
    "Oil filter",
    "Air filter element",
    "Wiper blade 22in",
    "Spark plug, iridium",
    "Serpentine belt",
    "Radiator hose, upper",
    "Headlamp bulb H7",
    "Cabin air filter",
    "Fuel pump relay",
    "Wheel bearing hub",
    "Tie rod end, outer",
    "Ball joint, lower",
    "Thermostat housing",
    "Belt tensioner",
    "Brake rotor, vented",
]
_VARIANTS = ["type A", "type B", "type C"]


def _harborline_items() -> tuple[Item, ...]:
    items = []
    n = 0
    for v_idx, variant in enumerate(_VARIANTS):
        for p_idx, part in enumerate(_PARTS):
            n += 1
            price = D(3 + (p_idx * 7 + v_idx * 5) % 90) + D((p_idx * 13 + v_idx * 29) % 100) / 100
            desc = f"{part}, {variant}".upper()
            items.append(Item(f"HFP-{5000 + n}", desc, desc.title(), price))
    return tuple(items)


HARBORLINE = Vendor(
    key="harborline",
    invoice_name="Harborline Fleet Parts LLC",
    po_name="Harborline Fleet Parts",
    address=("2 Nonexistent Wharf Road", "Port Example, ZZ 00003"),
    currency="USD",
    tax_rate=D("0.07"),
    tax_label="TAX 7%",
    inv_prefix="HFP ",
    style=Style(
        title="INVOICE",
        header="centered",
        labels={
            "number": "INV NO.",
            "date": "INV DATE",
            "due": "TERMS DUE",
            "po": "CUST PO#",
        },
        columns=("sku", "desc", "qty", "price", "amount"),
        column_titles={
            "sku": "SKU",
            "desc": "DESCRIPTION",
            "qty": "QTY",
            "price": "UNIT PRICE",
            "amount": "EXT PRICE",
        },
        totals={"subtotal": "SUBTOTAL", "total": "INVOICE TOTAL"},
        fmt_date=lambda d: d.isoformat(),
        fmt_money=plain_money,
        font="Courier",
        bold="Courier-Bold",
        rows_first_page=24,
        rows_next_page=34,
        currency_note="ALL AMOUNTS IN {cur}",
    ),
    items=_harborline_items(),
)

VENDORS = {v.key: v for v in (QUILLFEATHER, BRIGHTFORGE, KETTLEBY, PINECONE, HARBORLINE)}

BUYER = ("Sample Buyer Co. (fictional)", "Accounts Payable", "1 Placeholder Plaza, Demo City")
FOOTER = "Synthetic test document generated for invoice-agent. Not a real invoice."
