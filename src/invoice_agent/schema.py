"""Strict data models shared by every stage of the pipeline.

Money is always :class:`decimal.Decimal`. Floats never touch an amount.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

#: Decimal that serializes to a JSON string, so ``12.10`` never becomes ``12.1``.
Money = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]
Qty = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LineItem(_Strict):
    """One billed line on an invoice."""

    description: str
    quantity: Qty
    unit_price: Money
    amount: Money
    sku: str | None = None


class Invoice(_Strict):
    """Structured invoice produced by an extractor."""

    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: dt.date | None = None
    due_date: dt.date | None = None
    po_number: str | None = None
    currency: str | None = Field(default=None, description="ISO 4217 code, for example USD")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Money | None = Field(default=None, description="Sum of line amounts")
    discount: Money = Field(default=Decimal("0"), description="Invoice-level discount, positive")
    tax: Money | None = None
    total: Money | None = Field(default=None, description="subtotal - discount + tax")

    def missing_required(self) -> list[str]:
        """Return the names of fields that matching cannot run without."""
        required = ("vendor", "invoice_number", "currency", "total")
        missing = [name for name in required if getattr(self, name) in (None, "")]
        if not self.line_items:
            missing.append("line_items")
        return missing


class POLine(_Strict):
    line_no: int
    description: str
    quantity: Qty
    unit_price: Money
    sku: str | None = None


class PurchaseOrder(_Strict):
    po_number: str
    vendor: str
    currency: str
    lines: list[POLine]
    receipt_required: bool = Field(
        default=True,
        description="True for goods (3-way match). False for services (2-way match).",
    )


class ReceiptLine(_Strict):
    line_no: int
    quantity: Qty


class GoodsReceipt(_Strict):
    receipt_id: str
    po_number: str
    date: dt.date | None = None
    lines: list[ReceiptLine]


class Decision(StrEnum):
    AUTO_APPROVE = "auto_approve"
    NEEDS_REVIEW = "needs_review"
    REJECT = "reject"


class Severity(StrEnum):
    INFO = "info"
    REVIEW = "review"
    REJECT = "reject"


class Reason(_Strict):
    """A single explainable finding. ``code`` is stable; ``message`` is for humans."""

    code: str
    severity: Severity
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class LineMatch(_Strict):
    invoice_line: int
    po_line: int | None
    score: float
    method: str


class Result(_Strict):
    """Pipeline output for one invoice."""

    source: str | None = None
    decision: Decision
    invoice: Invoice
    po_number: str | None = None
    match_type: str | None = Field(default=None, description="2-way or 3-way")
    vendor_score: float | None = None
    line_matches: list[LineMatch] = Field(default_factory=list)
    reasons: list[Reason] = Field(default_factory=list)

    @property
    def reason_codes(self) -> list[str]:
        return [r.code for r in self.reasons]
