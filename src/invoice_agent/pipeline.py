"""End-to-end pipeline: ingest, extract, validate, match, decide."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .extract import Extractor, LayoutExtractor
from .ingest import Document, load_pdf
from .match import Ledger, Matcher
from .policy import MatchPolicy
from .reasons import reason
from .schema import (
    Decision,
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    Reason,
    Result,
    Severity,
)
from .validate import validate_arithmetic


def decide(reasons: Iterable[Reason]) -> Decision:
    """The strictest severity wins: any reject rejects, any review needs review."""
    severities = {r.severity for r in reasons}
    if Severity.REJECT in severities:
        return Decision.REJECT
    if Severity.REVIEW in severities:
        return Decision.NEEDS_REVIEW
    return Decision.AUTO_APPROVE


class Pipeline:
    """Process invoices one after another against the same PO data.

    The pipeline keeps a :class:`Ledger`, so the order of calls matters: a
    second invoice for the same goods is caught as a duplicate or as
    overbilling.
    """

    def __init__(
        self,
        purchase_orders: Iterable[PurchaseOrder],
        receipts: Iterable[GoodsReceipt] = (),
        *,
        extractor: Extractor | None = None,
        policy: MatchPolicy | None = None,
        ledger: Ledger | None = None,
        ocr: bool = False,
    ) -> None:
        self.policy = policy or MatchPolicy()
        self.extractor = extractor or LayoutExtractor()
        self.matcher = Matcher(purchase_orders, receipts, self.policy, ledger)
        self.ocr = ocr

    @property
    def ledger(self) -> Ledger:
        return self.matcher.ledger

    def process_pdf(self, source: str | Path | bytes, *, name: str | None = None) -> Result:
        doc = load_pdf(source, ocr=self.ocr, name=name)
        return self.process_document(doc)

    def process_document(self, doc: Document) -> Result:
        if not doc.has_text:
            reasons = [
                reason(
                    "NO_TEXT_LAYER",
                    "The PDF has no text layer (likely a scan). Run with OCR enabled or key it in.",
                )
            ]
            return Result(
                source=doc.source, decision=decide(reasons), invoice=Invoice(), reasons=reasons
            )
        invoice = self.extractor.extract(doc)
        return self.process_invoice(invoice, source=doc.source)

    def process_invoice(self, invoice: Invoice, *, source: str | None = None) -> Result:
        """Validate and match an already extracted invoice, then record it in the ledger."""
        reasons: list[Reason] = []
        missing = invoice.missing_required()
        if missing:
            reasons.append(
                reason(
                    "EXTRACTION_INCOMPLETE",
                    f"Could not read: {', '.join(missing)}.",
                    missing=missing,
                )
            )
        reasons.extend(validate_arithmetic(invoice, self.policy))
        outcome = self.matcher.match(invoice)
        reasons.extend(outcome.reasons)
        decision = decide(reasons)
        self.ledger.record(invoice, decision, outcome.po_number, outcome.line_matches, source)
        order = {Severity.REJECT: 0, Severity.REVIEW: 1, Severity.INFO: 2}
        reasons.sort(key=lambda r: order[r.severity])
        return Result(
            source=source,
            decision=decision,
            invoice=invoice,
            po_number=outcome.po_number,
            match_type=outcome.match_type,
            vendor_score=outcome.vendor_score,
            line_matches=outcome.line_matches,
            reasons=reasons,
        )
