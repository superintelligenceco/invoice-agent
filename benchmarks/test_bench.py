"""Benchmarks for the hot path: PDF ingest, layout extraction, and matching.

Run with `make bench`. `scripts/bench_check.py` compares the medians with `baseline.json` and
fails when a benchmark is more than twice as slow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from invoice_agent.data import load_purchase_orders, load_receipts
from invoice_agent.extract import LayoutExtractor
from invoice_agent.ingest import Document, load_pdf
from invoice_agent.pipeline import Pipeline
from invoice_agent.schema import GoodsReceipt, Invoice, PurchaseOrder

DATASET = Path(__file__).resolve().parent.parent / "dataset"
PDFS = sorted((DATASET / "invoices").glob("*.pdf"))


@pytest.fixture(scope="module")
def erp() -> tuple[list[PurchaseOrder], list[GoodsReceipt]]:
    return (
        load_purchase_orders(DATASET / "purchase_orders.json"),
        load_receipts(DATASET / "receipts.json"),
    )


@pytest.fixture(scope="module")
def invoices() -> list[Invoice]:
    out = []
    for path in sorted((DATASET / "ground_truth").glob("*.json")):
        data: dict[str, Any] = json.loads(path.read_text())
        out.append(Invoice.model_validate(data["invoice"]))
    return out


@pytest.fixture(scope="module")
def documents() -> list[Document]:
    return [load_pdf(p) for p in PDFS]


def test_bench_ingest_pdf(benchmark: Any) -> None:
    doc = benchmark(load_pdf, PDFS[0])
    assert doc.has_text


def test_bench_layout_extract(benchmark: Any, documents: list[Document]) -> None:
    extractor = LayoutExtractor()

    def run() -> list[Invoice]:
        return [extractor.extract(d) for d in documents if d.has_text]

    assert len(benchmark(run)) == len(documents) - 1  # one scanned invoice has no text


def test_bench_match_dataset(
    benchmark: Any,
    erp: tuple[list[PurchaseOrder], list[GoodsReceipt]],
    invoices: list[Invoice],
) -> None:
    pos, receipts = erp

    def run() -> int:
        pipeline = Pipeline(pos, receipts)
        return sum(1 for inv in invoices if pipeline.process_invoice(inv).decision)

    assert benchmark(run) == len(invoices)
