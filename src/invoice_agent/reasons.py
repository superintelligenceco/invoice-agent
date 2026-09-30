"""Catalog of reason codes. Codes are stable; messages are generated per invoice."""

from __future__ import annotations

from typing import Any

from .schema import Reason, Severity

#: code -> (severity, one-line meaning). The README reference table is built from this.
CODES: dict[str, tuple[Severity, str]] = {
    "NO_TEXT_LAYER": (
        Severity.REVIEW,
        "The PDF has no extractable text. Enable OCR or key the invoice in by hand.",
    ),
    "EXTRACTION_INCOMPLETE": (
        Severity.REVIEW,
        "A field that matching needs (vendor, number, currency, total, lines) is missing.",
    ),
    "LINE_ROUNDING": (
        Severity.INFO,
        "A line amount differs from quantity x unit price by a rounding amount.",
    ),
    "LINE_AMOUNT_MISMATCH": (
        Severity.REVIEW,
        "A line amount differs from quantity x unit price by more than rounding.",
    ),
    "SUBTOTAL_MISMATCH": (Severity.REVIEW, "Line amounts do not add up to the printed subtotal."),
    "TOTAL_MISMATCH": (
        Severity.REVIEW,
        "Subtotal minus discount plus tax does not equal the printed total.",
    ),
    "DUPLICATE_INVOICE": (
        Severity.REJECT,
        "Same vendor and same invoice number as an invoice already processed.",
    ),
    "POSSIBLE_DUPLICATE": (
        Severity.REVIEW,
        "Same vendor, currency and total as a recent invoice, under a different number.",
    ),
    "PO_MISSING": (
        Severity.REVIEW,
        "No PO number is printed. The matcher may infer one from the vendor's open POs.",
    ),
    "PO_NOT_FOUND": (Severity.REVIEW, "The printed PO number does not exist in the PO data."),
    "VENDOR_MISMATCH": (Severity.REJECT, "The PO was issued to a different vendor."),
    "CURRENCY_MISMATCH": (
        Severity.REVIEW,
        "The invoice currency differs from the PO currency. Prices are not compared.",
    ),
    "LINE_NOT_ON_PO": (Severity.REVIEW, "An invoice line has no matching PO line."),
    "PRICE_VARIANCE": (
        Severity.REVIEW,
        "A unit price is above the PO price by more than the tolerance.",
    ),
    "PRICE_BELOW_PO": (Severity.INFO, "A unit price is below the PO price."),
    "QTY_EXCEEDS_ORDERED": (
        Severity.REJECT,
        "Billed quantity, including earlier invoices, exceeds the ordered quantity.",
    ),
    "QTY_EXCEEDS_RECEIVED": (
        Severity.REVIEW,
        "Billed quantity, including earlier invoices, exceeds the received quantity (3-way).",
    ),
    "PO_LINES_OPEN": (Severity.INFO, "Some PO lines are not billed yet (partial invoicing)."),
}


def reason(code: str, message: str, **data: Any) -> Reason:
    """Build a :class:`Reason` with the catalog severity for ``code``."""
    severity, _ = CODES[code]
    return Reason(code=code, severity=severity, message=message, data=data)
