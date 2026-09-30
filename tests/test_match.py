from __future__ import annotations

from decimal import Decimal

import pytest

from invoice_agent.match import Ledger, Matcher, align_lines, vendor_similarity
from invoice_agent.pipeline import Pipeline, decide
from invoice_agent.policy import MatchPolicy
from invoice_agent.schema import (
    Decision,
    GoodsReceipt,
    LineItem,
    POLine,
    PurchaseOrder,
    ReceiptLine,
    Result,
    Severity,
)

from .conftest import make_invoice

D = Decimal
FULL = [("Blue widget, large", "W-100", 10, "5.00"), ("Red gadget, small", "W-200", 4, "20.00")]


def run(
    pos: list[PurchaseOrder], receipts: list[GoodsReceipt], *invoices, policy=None
) -> list[Result]:  # type: ignore[no-untyped-def]
    p = Pipeline(pos, receipts, policy=policy)
    return [p.process_invoice(inv, source=f"inv{i}") for i, inv in enumerate(invoices, start=1)]


def flagged(result: Result) -> list[str]:
    return sorted(r.code for r in result.reasons if r.severity is not Severity.INFO)


def test_clean_three_way_match(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    (res,) = run([po], [receipt], make_invoice(FULL))
    assert res.decision is Decision.AUTO_APPROVE
    assert res.match_type == "3-way"
    assert res.po_number == "PO-1"
    assert [m.po_line for m in res.line_matches] == [1, 2]
    assert all(m.method == "sku" for m in res.line_matches)


def test_price_within_tolerance_is_approved(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([("Blue widget, large", "W-100", 10, "5.05")])  # +1%, abs 0.05
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.AUTO_APPROVE
    assert "PO_LINES_OPEN" in res.reason_codes


def test_price_above_tolerance_needs_review(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([("Red gadget, small", "W-200", 4, "21.00")])  # +5%
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.NEEDS_REVIEW
    assert flagged(res) == ["PRICE_VARIANCE"]
    assert "5.0% above" in res.reasons[0].message


def test_price_tolerance_uses_the_larger_of_pct_and_abs(
    po: PurchaseOrder, receipt: GoodsReceipt
) -> None:
    inv = make_invoice([("Red gadget, small", "W-200", 4, "21.00")])
    policy = MatchPolicy(price_tolerance_pct=D("0.01"), price_tolerance_abs=D("1.00"))
    (res,) = run([po], [receipt], inv, policy=policy)
    assert res.decision is Decision.AUTO_APPROVE


def test_price_below_po_is_info(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([("Blue widget, large", "W-100", 10, "4.50")])
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.AUTO_APPROVE
    assert "PRICE_BELOW_PO" in res.reason_codes


def test_quantity_over_ordered_is_rejected(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([("Blue widget, large", "W-100", 12, "5.00")])
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.REJECT
    assert flagged(res) == ["QTY_EXCEEDS_ORDERED"]


def test_quantity_tolerance(po: PurchaseOrder) -> None:
    inv = make_invoice([("Blue widget, large", "W-100", 11, "5.00")])
    two_way = po.model_copy(update={"receipt_required": False})
    (res,) = run([two_way], [], inv, policy=MatchPolicy(qty_tolerance_pct=D("0.10")))
    assert res.decision is Decision.AUTO_APPROVE


def test_partial_receipts_are_summed(po: PurchaseOrder) -> None:
    receipts = [
        GoodsReceipt(
            receipt_id="GR-1", po_number="PO-1", lines=[ReceiptLine(line_no=1, quantity=D(3))]
        ),
        GoodsReceipt(
            receipt_id="GR-2", po_number="po 1", lines=[ReceiptLine(line_no=1, quantity=D(4))]
        ),
    ]
    ok, over = run(
        [po],
        receipts,
        make_invoice([("Blue widget, large", "W-100", 7, "5.00")], number="A"),
        make_invoice([("Blue widget, large", "W-100", 1, "5.00")], number="B", date="2026-05-01"),
    )
    assert ok.decision is Decision.AUTO_APPROVE
    assert over.decision is Decision.NEEDS_REVIEW
    assert flagged(over) == ["QTY_EXCEEDS_RECEIVED"]
    assert "7 on earlier invoices" in over.reasons[0].message


def test_goods_not_received_needs_review(po: PurchaseOrder) -> None:
    (res,) = run([po], [], make_invoice(FULL))
    assert res.decision is Decision.NEEDS_REVIEW
    assert flagged(res) == ["QTY_EXCEEDS_RECEIVED", "QTY_EXCEEDS_RECEIVED"]


def test_two_way_match_ignores_receipts(po: PurchaseOrder) -> None:
    services = po.model_copy(update={"receipt_required": False})
    (res,) = run([services], [], make_invoice(FULL))
    assert res.decision is Decision.AUTO_APPROVE
    assert res.match_type == "2-way"


def test_cumulative_overbilling_across_invoices(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    first, second = run(
        [po],
        [receipt],
        make_invoice([("Blue widget, large", "W-100", 6, "5.00")], number="A"),
        make_invoice([("Blue widget, large", "W-100", 6, "5.00")], number="B", date="2026-05-01"),
    )
    assert first.decision is Decision.AUTO_APPROVE
    assert second.decision is Decision.REJECT
    assert "billed 12 (6 on earlier invoices), ordered 10" in second.reasons[0].message


def test_rejected_invoices_do_not_consume_the_po(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    over, fine = run(
        [po],
        [receipt],
        make_invoice([("Blue widget, large", "W-100", 20, "5.00")], number="A"),
        make_invoice([("Blue widget, large", "W-100", 10, "5.00")], number="B", date="2026-05-01"),
    )
    assert over.decision is Decision.REJECT
    assert fine.decision is Decision.AUTO_APPROVE


def test_exact_duplicate_is_rejected(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice(FULL, number="INV-2026/001")
    again = inv.model_copy(update={"invoice_number": "inv 2026-001"})
    first, dup = run([po], [receipt], inv, again)
    assert first.decision is Decision.AUTO_APPROVE
    assert dup.decision is Decision.REJECT
    assert dup.reason_codes == ["DUPLICATE_INVOICE"]
    assert dup.po_number == "PO-1"
    assert "inv1" in dup.reasons[0].message


def test_possible_duplicate_same_total_new_number(po: PurchaseOrder) -> None:
    services = po.model_copy(update={"receipt_required": False})
    half = [("Blue widget, large", "W-100", 4, "5.00")]
    a, b, c = run(
        [services],
        [],
        make_invoice(half, number="A", date="2026-03-01"),
        make_invoice(half, number="B", date="2026-03-05"),
        make_invoice([("Blue widget, large", "W-100", 1, "5.00")], number="C"),
    )
    assert a.decision is Decision.AUTO_APPROVE
    assert b.decision is Decision.NEEDS_REVIEW
    assert flagged(b) == ["POSSIBLE_DUPLICATE"]
    assert flagged(c) == []


def test_possible_duplicate_outside_window_is_ignored(po: PurchaseOrder) -> None:
    services = po.model_copy(update={"receipt_required": False})
    half = [("Blue widget, large", "W-100", 4, "5.00")]
    _, later = run(
        [services],
        [],
        make_invoice(half, number="A", date="2026-03-01"),
        make_invoice(half, number="B", date="2026-04-30"),
    )
    assert later.decision is Decision.AUTO_APPROVE


def test_vendor_mismatch_is_rejected(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    (res,) = run([po], [receipt], make_invoice(FULL, vendor="Totally Different Traders Inc"))
    assert res.decision is Decision.REJECT
    assert res.reason_codes == ["VENDOR_MISMATCH"]


def test_currency_mismatch_skips_price_checks(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([("Blue widget, large", "W-100", 10, "9.00")], currency="EUR")
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.NEEDS_REVIEW
    assert flagged(res) == ["CURRENCY_MISMATCH"]


def test_po_not_found(po: PurchaseOrder) -> None:
    (res,) = run([po], [], make_invoice(FULL, po_number="PO-404"))
    assert res.decision is Decision.NEEDS_REVIEW
    assert res.reason_codes == ["PO_NOT_FOUND"]
    assert res.po_number is None


def test_missing_po_is_inferred(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    other = PurchaseOrder(
        po_number="PO-2",
        vendor=po.vendor,
        currency="USD",
        lines=[POLine(line_no=1, description="Green thing", quantity=D(1), unit_price=D("1.00"))],
    )
    (res,) = run([other, po], [receipt], make_invoice(FULL, po_number=None))
    assert res.decision is Decision.NEEDS_REVIEW
    assert res.po_number == "PO-1"
    assert flagged(res) == ["PO_MISSING"]
    assert res.reasons[0].data["inferred_po"] == "PO-1"


def test_missing_po_can_auto_approve_when_policy_allows(
    po: PurchaseOrder, receipt: GoodsReceipt
) -> None:
    policy = MatchPolicy(require_po_number=False)
    (res,) = run([po], [receipt], make_invoice(FULL, po_number=None), policy=policy)
    assert res.decision is Decision.AUTO_APPROVE
    assert res.po_number == "PO-1"


def test_missing_po_ambiguous_is_not_guessed(po: PurchaseOrder) -> None:
    twin = po.model_copy(update={"po_number": "PO-9"})
    (res,) = run([po, twin], [], make_invoice(FULL, po_number=None))
    assert res.po_number is None
    assert "Several POs fit" in res.reasons[0].message


def test_line_not_on_po(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice([*FULL, ("Freight surcharge", "FRT-1", 1, "15.00")])
    (res,) = run([po], [receipt], inv)
    assert res.decision is Decision.NEEDS_REVIEW
    assert flagged(res) == ["LINE_NOT_ON_PO"]
    assert res.line_matches[2].po_line is None


def test_incomplete_extraction_needs_review(po: PurchaseOrder, receipt: GoodsReceipt) -> None:
    inv = make_invoice(FULL).model_copy(update={"invoice_number": None})
    (res,) = run([po], [receipt], inv)
    assert "EXTRACTION_INCOMPLETE" in res.reason_codes
    assert res.decision is Decision.NEEDS_REVIEW


def test_align_lines_by_description_without_skus() -> None:
    po_lines = [
        POLine(
            line_no=1, description="A4 copy paper 80gsm 500 sheets", quantity=D(1), unit_price=D(1)
        ),
        POLine(line_no=2, description="Blue ballpoint pen box/50", quantity=D(1), unit_price=D(1)),
    ]
    lines = [
        LineItem(
            description="Ballpoint pens, blue, box of 50",
            quantity=D(1),
            unit_price=D(1),
            amount=D(1),
        ),
        LineItem(
            description="Copy paper A4 80gsm, ream of 500",
            quantity=D(1),
            unit_price=D(1),
            amount=D(1),
        ),
        LineItem(description="Espresso machine", quantity=D(1), unit_price=D(1), amount=D(1)),
    ]
    matches = align_lines(lines, po_lines, threshold=0.55)
    assert [m.po_line for m in matches] == [2, 1, None]
    assert matches[0].method == "description"


def test_align_lines_different_skus_never_pair() -> None:
    po_lines = [
        POLine(
            line_no=1, sku="A-1", description="Brake pad, type A", quantity=D(1), unit_price=D(1)
        )
    ]
    lines = [
        LineItem(
            sku="A-2", description="Brake pad, type A", quantity=D(1), unit_price=D(1), amount=D(1)
        )
    ]
    assert align_lines(lines, po_lines, threshold=0.5)[0].po_line is None


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Kettleby Lab Consumables Ltd", "Kettleby Laboratory Consumables Limited", True),
        ("Pinecone Cloud Services Inc.", "Pinecone Cloud Services, Inc", True),
        ("Quillfeather Office Supply Co.", "Harborline Fleet Parts", False),
        (None, "Anything", False),
    ],
)
def test_vendor_similarity(a: str | None, b: str, same: bool) -> None:
    assert (vendor_similarity(a, b) >= MatchPolicy().vendor_match_threshold) is same


def test_ledger_roundtrip(tmp_path, po: PurchaseOrder, receipt: GoodsReceipt) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "ledger.json"
    first = Pipeline([po], [receipt])
    first.process_invoice(make_invoice(FULL), source="a.pdf")
    first.ledger.save(path)

    second = Pipeline([po], [receipt], ledger=Ledger.load(path))
    res = second.process_invoice(make_invoice(FULL, number="INV-2", date="2026-06-01"))
    assert res.decision is Decision.REJECT
    assert "QTY_EXCEEDS_ORDERED" in res.reason_codes
    assert Ledger.load(tmp_path / "missing.json").seen == []


def test_matcher_without_ledger_starts_empty(po: PurchaseOrder) -> None:
    assert Matcher([po]).ledger.seen == []


def test_decide_takes_the_strictest_severity() -> None:
    assert decide([]) is Decision.AUTO_APPROVE
    (res,) = run([], [], make_invoice(FULL))
    assert res.decision is Decision.NEEDS_REVIEW  # PO_NOT_FOUND
