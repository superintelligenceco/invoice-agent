"""Process the shipped dataset from Python and print one line per invoice.

Run from the repository root:

    python examples/python_api.py
"""

from __future__ import annotations

from pathlib import Path

from invoice_agent.data import load_purchase_orders, load_receipts
from invoice_agent.pipeline import Pipeline

DATASET = Path("dataset")

pipeline = Pipeline(
    load_purchase_orders(DATASET / "purchase_orders.json"),
    load_receipts(DATASET / "receipts.json"),
)

for pdf in sorted((DATASET / "invoices").glob("*.pdf")):
    result = pipeline.process_pdf(pdf)
    codes = ", ".join(r.code for r in result.reasons if r.severity != "info") or "-"
    print(f"{pdf.name:<16} {result.decision.value:<13} {result.po_number or '-':<14} {codes}")
