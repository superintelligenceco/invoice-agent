from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from invoice_agent.extract import LayoutExtractor, LLMExtractor, get_extractor
from invoice_agent.ingest import Document, load_pdf
from invoice_agent.schema import Invoice

from .conftest import DATASET, truth

TEXT_LAYER_PDFS = sorted(
    p.stem for p in (DATASET / "invoices").glob("*.pdf") if not p.stem.endswith("q10")
)


@pytest.mark.parametrize("stem", TEXT_LAYER_PDFS)
def test_layout_extractor_matches_ground_truth(stem: str) -> None:
    expected = Invoice.model_validate(truth(stem)["invoice"])
    got = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / f"{stem}.pdf"))
    assert got == expected


def test_european_number_and_date_format() -> None:
    inv = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / "013_b01.pdf"))
    assert inv.currency == "EUR"
    assert inv.invoice_date is not None
    assert inv.invoice_date.isoformat() == "2026-03-14"
    assert inv.line_items[0].sku == "BF-40110"


def test_multi_page_invoice_keeps_every_line() -> None:
    inv = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / "042_h02.pdf"))
    doc = load_pdf(DATASET / "invoices" / "042_h02.pdf")
    assert len(doc.pages) == 2
    assert len(inv.line_items) == 45
    assert sum(li.amount for li in inv.line_items) == inv.subtotal


def test_wrapped_descriptions_are_joined() -> None:
    inv = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / "024_k02.pdf"))
    assert inv.line_items[0].description.startswith("Serological pipettes, 10 mL")
    assert inv.line_items[0].description.endswith("case of 200")


def test_discount_is_read_as_positive() -> None:
    inv = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / "033_p02.pdf"))
    assert inv.discount > Decimal(0)
    assert inv.subtotal is not None
    assert inv.total is not None
    assert inv.subtotal - inv.discount + (inv.tax or 0) == inv.total


def test_missing_po_number_stays_none() -> None:
    inv = LayoutExtractor().extract(load_pdf(DATASET / "invoices" / "005_q05.pdf"))
    assert inv.po_number is None
    assert inv.invoice_number


def test_empty_document_gives_empty_invoice() -> None:
    assert LayoutExtractor().extract(Document(source="x", pages=[""])) == Invoice()


def test_plain_text_invoice() -> None:
    text = """Northwind Test Supplies Ltd
INVOICE
Invoice No: NW-77
Invoice Date: 2026-01-15
PO Number: PO-2026-0001
Description Qty Unit Price Amount
Widget, blue 2 $10.00 $20.00
Widget, red 1 $5.50 $5.50
Subtotal $25.50
Tax $0.00
Total $25.50
"""
    inv = LayoutExtractor().extract(Document(source="t", pages=[text]))
    assert inv.vendor == "Northwind Test Supplies Ltd"
    assert inv.invoice_number == "NW-77"
    assert inv.po_number == "PO-2026-0001"
    assert inv.currency == "USD"
    assert [li.amount for li in inv.line_items] == [Decimal("20.00"), Decimal("5.50")]
    assert inv.total == Decimal("25.50")


def test_get_extractor() -> None:
    assert isinstance(get_extractor("layout"), LayoutExtractor)
    assert isinstance(get_extractor("llm"), LLMExtractor)
    with pytest.raises(ValueError, match="unknown extractor"):
        get_extractor("magic")


def test_scanned_pdf_has_no_text() -> None:
    doc = load_pdf(DATASET / "invoices" / "010_q10.pdf")
    assert not doc.has_text


def test_load_pdf_from_bytes_and_rejects_non_pdf(tmp_path: Path) -> None:
    data = (DATASET / "invoices" / "001_q01.pdf").read_bytes()
    assert load_pdf(data, name="upload.pdf").source == "upload.pdf"
    bad = tmp_path / "x.pdf"
    bad.write_text("hello")
    from invoice_agent.ingest import IngestError

    with pytest.raises(IngestError, match="not a PDF"):
        load_pdf(bad)
