"""Two-way and three-way matching of invoices against POs and goods receipts.

The matcher is stateful on purpose. A :class:`Ledger` remembers every invoice
it has seen and how much of each PO line is already billed, so it can catch
duplicate submissions and cumulative overbilling across several invoices.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, utils

from .normalize import normalize_doc_number, normalize_po, normalize_vendor
from .policy import MatchPolicy
from .reasons import reason
from .schema import (
    Decision,
    GoodsReceipt,
    Invoice,
    LineItem,
    LineMatch,
    POLine,
    PurchaseOrder,
    Reason,
)

ZERO = Decimal("0")


def vendor_similarity(a: str | None, b: str | None) -> float:
    """Fuzzy similarity (0-100) of two vendor names after dropping legal suffixes."""
    na, nb = normalize_vendor(a), normalize_vendor(b)
    if not na or not nb:
        return 0.0
    return float(max(fuzz.token_set_ratio(na, nb), fuzz.token_sort_ratio(na, nb)))


def description_similarity(a: str, b: str) -> float:
    """Similarity (0-1) of two line descriptions, insensitive to case, order and punctuation."""
    return float(fuzz.token_set_ratio(a, b, processor=utils.default_process)) / 100.0


@dataclass
class SeenInvoice:
    vendor: str
    invoice_number: str
    total: Decimal | None
    currency: str | None
    invoice_date: dt.date | None
    source: str | None
    decision: str


@dataclass
class Ledger:
    """Invoices processed so far, and billed quantity per ``(PO, line)``."""

    seen: list[SeenInvoice] = field(default_factory=list)
    billed: dict[tuple[str, int], Decimal] = field(default_factory=lambda: defaultdict(Decimal))

    def billed_qty(self, po_number: str, line_no: int) -> Decimal:
        return self.billed.get((normalize_po(po_number), line_no), ZERO)

    def record(
        self,
        invoice: Invoice,
        decision: Decision,
        po_number: str | None,
        matches: Iterable[LineMatch],
        source: str | None = None,
    ) -> None:
        """Remember an invoice. Quantities count as billed unless it was rejected."""
        self.seen.append(
            SeenInvoice(
                vendor=invoice.vendor or "",
                invoice_number=invoice.invoice_number or "",
                total=invoice.total,
                currency=invoice.currency,
                invoice_date=invoice.invoice_date,
                source=source,
                decision=decision.value,
            )
        )
        if decision is Decision.REJECT or not po_number:
            return
        for m in matches:
            if m.po_line is None:
                continue
            key = (normalize_po(po_number), m.po_line)
            self.billed[key] = (
                self.billed.get(key, ZERO) + invoice.line_items[m.invoice_line - 1].quantity
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seen": [
                {
                    **s.__dict__,
                    "total": None if s.total is None else str(s.total),
                    "invoice_date": s.invoice_date.isoformat() if s.invoice_date else None,
                }
                for s in self.seen
            ],
            "billed": [
                {"po": po, "line": line, "quantity": str(q)}
                for (po, line), q in self.billed.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ledger:
        ledger = cls()
        for s in data.get("seen", []):
            ledger.seen.append(
                SeenInvoice(
                    vendor=s["vendor"],
                    invoice_number=s["invoice_number"],
                    total=None if s.get("total") is None else Decimal(s["total"]),
                    currency=s.get("currency"),
                    invoice_date=dt.date.fromisoformat(s["invoice_date"])
                    if s.get("invoice_date")
                    else None,
                    source=s.get("source"),
                    decision=s["decision"],
                )
            )
        for b in data.get("billed", []):
            ledger.billed[(b["po"], int(b["line"]))] = Decimal(b["quantity"])
        return ledger

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Ledger:
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))


@dataclass
class MatchOutcome:
    po_number: str | None = None
    match_type: str | None = None
    vendor_score: float | None = None
    line_matches: list[LineMatch] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)


def align_lines(lines: list[LineItem], po_lines: list[POLine], threshold: float) -> list[LineMatch]:
    """Pair invoice lines with PO lines, one-to-one.

    A SKU match scores 1.0. Otherwise the description similarity is used, and
    pairs below ``threshold`` stay unmatched. Lines where both sides carry a
    different SKU never pair. Pairs are assigned greedily, best score first.
    """
    candidates: list[tuple[float, int, int, str]] = []
    for i, li in enumerate(lines):
        inv_sku = normalize_doc_number(li.sku)
        for j, pl in enumerate(po_lines):
            po_sku = normalize_doc_number(pl.sku)
            if inv_sku and po_sku:
                if inv_sku == po_sku:
                    candidates.append(
                        (
                            1.0 + description_similarity(li.description, pl.description) / 10,
                            i,
                            j,
                            "sku",
                        )
                    )
                continue
            score = description_similarity(li.description, pl.description)
            if score >= threshold:
                candidates.append((score, i, j, "description"))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    taken_inv: dict[int, LineMatch] = {}
    taken_po: set[int] = set()
    for score, i, j, method in candidates:
        if i in taken_inv or j in taken_po:
            continue
        taken_inv[i] = LineMatch(
            invoice_line=i + 1,
            po_line=po_lines[j].line_no,
            score=round(min(score, 1.0), 3),
            method=method,
        )
        taken_po.add(j)
    return [
        taken_inv.get(i, LineMatch(invoice_line=i + 1, po_line=None, score=0.0, method="none"))
        for i in range(len(lines))
    ]


class Matcher:
    """Matches invoices against a fixed set of POs and receipts."""

    def __init__(
        self,
        purchase_orders: Iterable[PurchaseOrder],
        receipts: Iterable[GoodsReceipt] = (),
        policy: MatchPolicy | None = None,
        ledger: Ledger | None = None,
    ) -> None:
        self.policy = policy or MatchPolicy()
        self.ledger = ledger if ledger is not None else Ledger()
        self.pos: dict[str, PurchaseOrder] = {
            normalize_po(po.po_number): po for po in purchase_orders
        }
        self.received: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
        for r in receipts:
            for line in r.lines:
                self.received[(normalize_po(r.po_number), line.line_no)] += line.quantity

    # -- duplicates ---------------------------------------------------------
    def check_duplicates(self, inv: Invoice) -> list[Reason]:
        number = normalize_doc_number(inv.invoice_number)
        possible: list[Reason] = []
        for s in self.ledger.seen:
            if vendor_similarity(inv.vendor, s.vendor) < self.policy.vendor_match_threshold:
                continue
            where = f" ({s.source})" if s.source else ""
            if number and number == normalize_doc_number(s.invoice_number):
                return [
                    reason(
                        "DUPLICATE_INVOICE",
                        f"Invoice {inv.invoice_number} from {inv.vendor} was already processed"
                        f"{where} as {s.invoice_number}, decision {s.decision}.",
                        previous=s.invoice_number,
                        previous_source=s.source,
                    )
                ]
            if (
                not possible
                and inv.total is not None
                and inv.total == s.total
                and inv.currency == s.currency
                and inv.invoice_date
                and s.invoice_date
                and abs((inv.invoice_date - s.invoice_date).days)
                <= self.policy.duplicate_window_days
            ):
                possible.append(
                    reason(
                        "POSSIBLE_DUPLICATE",
                        f"Same vendor, currency and total ({inv.currency} {inv.total}) as invoice "
                        f"{s.invoice_number}{where}, dated {s.invoice_date.isoformat()}.",
                        previous=s.invoice_number,
                        previous_source=s.source,
                    )
                )
        return possible

    # -- PO lookup ----------------------------------------------------------
    def find_po(self, inv: Invoice) -> tuple[PurchaseOrder | None, list[Reason]]:
        if inv.po_number:
            po = self.pos.get(normalize_po(inv.po_number))
            if po is None:
                return None, [
                    reason(
                        "PO_NOT_FOUND",
                        f"PO {inv.po_number} printed on the invoice does not exist.",
                        po_number=inv.po_number,
                    )
                ]
            return po, []
        inferred, note = self.infer_po(inv)
        severity_note = " Review the inferred PO before approving." if inferred else ""
        reasons = [
            reason(
                "PO_MISSING",
                f"The invoice shows no PO number. {note}{severity_note}",
                inferred_po=inferred.po_number if inferred else None,
            )
        ]
        if not self.policy.require_po_number and inferred is not None:
            reasons = []
        return inferred, reasons

    def infer_po(self, inv: Invoice) -> tuple[PurchaseOrder | None, str]:
        """Pick the vendor's open PO whose lines best fit the invoice."""
        scored: list[tuple[float, PurchaseOrder]] = []
        for po in self.pos.values():
            if vendor_similarity(inv.vendor, po.vendor) < self.policy.vendor_match_threshold:
                continue
            if inv.currency and inv.currency != po.currency:
                continue
            matches = align_lines(inv.line_items, po.lines, self.policy.line_match_threshold)
            by_no = {pl.line_no: pl for pl in po.lines}
            points = 0.0
            for m in matches:
                if m.po_line is None:
                    continue
                pl = by_no[m.po_line]
                open_qty = pl.quantity - self.ledger.billed_qty(po.po_number, pl.line_no)
                qty = inv.line_items[m.invoice_line - 1].quantity
                points += 1.0 if qty == open_qty else 0.5 if qty <= open_qty else 0.1
            score = points / max(len(inv.line_items), len(po.lines), 1)
            if score > 0:
                scored.append((score, po))
        scored.sort(key=lambda s: -s[0])
        if not scored or scored[0][0] < 0.5:
            return None, "No open PO from this vendor fits the invoice lines."
        if len(scored) > 1 and scored[1][0] >= scored[0][0] - 0.1:
            return None, (
                f"Several POs fit equally well ({scored[0][1].po_number}, "
                f"{scored[1][1].po_number})."
            )
        best = scored[0]
        return best[1], f"PO {best[1].po_number} fits the invoice lines (score {best[0]:.2f})."

    # -- matching -----------------------------------------------------------
    def match(self, inv: Invoice) -> MatchOutcome:
        out = MatchOutcome()
        dups = self.check_duplicates(inv)
        out.reasons.extend(dups)
        if any(r.code == "DUPLICATE_INVOICE" for r in dups):
            printed = self.pos.get(normalize_po(inv.po_number)) if inv.po_number else None
            out.po_number = printed.po_number if printed else None
            return out

        po, po_reasons = self.find_po(inv)
        out.reasons.extend(po_reasons)
        if po is None:
            return out
        out.po_number = po.po_number
        out.match_type = "3-way" if po.receipt_required else "2-way"

        out.vendor_score = round(vendor_similarity(inv.vendor, po.vendor), 1)
        if out.vendor_score < self.policy.vendor_match_threshold:
            out.reasons.append(
                reason(
                    "VENDOR_MISMATCH",
                    f"PO {po.po_number} was issued to {po.vendor!r}, not {inv.vendor!r} "
                    f"(similarity {out.vendor_score:.0f}/100).",
                    po_vendor=po.vendor,
                    invoice_vendor=inv.vendor,
                )
            )
            return out

        compare_prices = True
        if inv.currency and inv.currency != po.currency:
            compare_prices = False
            out.reasons.append(
                reason(
                    "CURRENCY_MISMATCH",
                    f"Invoice is in {inv.currency}, PO {po.po_number} is in {po.currency}.",
                    invoice_currency=inv.currency,
                    po_currency=po.currency,
                )
            )

        out.line_matches = align_lines(inv.line_items, po.lines, self.policy.line_match_threshold)
        by_no = {pl.line_no: pl for pl in po.lines}
        for m in out.line_matches:
            li = inv.line_items[m.invoice_line - 1]
            if m.po_line is None:
                out.reasons.append(
                    reason(
                        "LINE_NOT_ON_PO",
                        f"Line {m.invoice_line} ({li.description!r}, {li.quantity} x "
                        f"{li.unit_price}) has no matching line on PO {po.po_number}.",
                        line=m.invoice_line,
                    )
                )
                continue
            out.reasons.extend(
                self._check_line(po, by_no[m.po_line], m.invoice_line, li, compare_prices)
            )

        billed_lines = {m.po_line for m in out.line_matches if m.po_line is not None}
        open_lines = [pl.line_no for pl in po.lines if pl.line_no not in billed_lines]
        if open_lines and inv.line_items:
            out.reasons.append(
                reason(
                    "PO_LINES_OPEN",
                    f"PO {po.po_number} lines {', '.join(map(str, open_lines))} "
                    "are not on this invoice.",
                    lines=open_lines,
                )
            )
        return out

    def _check_line(
        self, po: PurchaseOrder, pl: POLine, n: int, li: LineItem, compare_prices: bool
    ) -> list[Reason]:
        p = self.policy
        reasons: list[Reason] = []
        label = f"Line {n} ({li.description!r}, PO line {pl.line_no})"
        if compare_prices:
            allowed = max(pl.unit_price * p.price_tolerance_pct, p.price_tolerance_abs)
            diff = li.unit_price - pl.unit_price
            if diff > allowed:
                pct = diff / pl.unit_price * 100 if pl.unit_price else Decimal("100")
                reasons.append(
                    reason(
                        "PRICE_VARIANCE",
                        f"{label}: unit price {li.unit_price} is {pct:.1f}% above the PO price "
                        f"{pl.unit_price} (tolerance {p.price_tolerance_pct * 100:.1f}% or "
                        f"{p.price_tolerance_abs}).",
                        line=n,
                        po_line=pl.line_no,
                        invoice_price=str(li.unit_price),
                        po_price=str(pl.unit_price),
                    )
                )
            elif diff < 0:
                reasons.append(
                    reason(
                        "PRICE_BELOW_PO",
                        f"{label}: unit price {li.unit_price} is below the PO price "
                        f"{pl.unit_price}.",
                        line=n,
                        po_line=pl.line_no,
                    )
                )

        prior = self.ledger.billed_qty(po.po_number, pl.line_no)
        cumulative = prior + li.quantity
        earlier = f" ({prior} on earlier invoices)" if prior else ""
        ordered_limit = pl.quantity * (1 + p.qty_tolerance_pct)
        if cumulative > ordered_limit:
            reasons.append(
                reason(
                    "QTY_EXCEEDS_ORDERED",
                    f"{label}: billed {cumulative}{earlier}, ordered {pl.quantity}.",
                    line=n,
                    po_line=pl.line_no,
                    billed=str(cumulative),
                    ordered=str(pl.quantity),
                )
            )
        elif po.receipt_required:
            received = self.received.get((normalize_po(po.po_number), pl.line_no), ZERO)
            if cumulative > received * (1 + p.qty_tolerance_pct):
                reasons.append(
                    reason(
                        "QTY_EXCEEDS_RECEIVED",
                        f"{label}: billed {cumulative}{earlier}, received {received}.",
                        line=n,
                        po_line=pl.line_no,
                        billed=str(cumulative),
                        received=str(received),
                    )
                )
        return reasons
