from __future__ import annotations

from decimal import Decimal

from invoice_agent.policy import MatchPolicy
from invoice_agent.schema import LineItem, Reason, Severity
from invoice_agent.validate import validate_arithmetic

from .conftest import make_invoice


def codes(reasons: list[Reason]) -> list[str]:
    return [r.code for r in reasons]


def test_clean_invoice_has_no_findings() -> None:
    inv = make_invoice([("Blue widget", None, 3, "5.00")], tax_rate="0.10")
    assert validate_arithmetic(inv) == []


def test_one_cent_rounding_is_info_only() -> None:
    inv = make_invoice([("Blue widget", None, 3, "5.00")])
    li = inv.line_items[0]
    inv = inv.model_copy(
        update={
            "line_items": [li.model_copy(update={"amount": Decimal("15.01")})],
            "subtotal": Decimal("15.01"),
            "total": Decimal("15.01"),
        }
    )
    reasons = validate_arithmetic(inv)
    assert codes(reasons) == ["LINE_ROUNDING"]
    assert reasons[0].severity is Severity.INFO


def test_line_amount_mismatch() -> None:
    inv = make_invoice([("Blue widget", None, 3, "5.00")])
    bad = LineItem(
        description="Blue widget",
        quantity=Decimal(3),
        unit_price=Decimal("5.00"),
        amount=Decimal("18.00"),
    )
    inv = inv.model_copy(
        update={"line_items": [bad], "subtotal": Decimal("18.00"), "total": Decimal("18.00")}
    )
    assert codes(validate_arithmetic(inv)) == ["LINE_AMOUNT_MISMATCH"]


def test_subtotal_mismatch() -> None:
    inv = make_invoice([("A", None, 1, "10.00"), ("B", None, 2, "5.00")])
    inv = inv.model_copy(update={"subtotal": Decimal("25.00"), "total": Decimal("25.00")})
    reasons = validate_arithmetic(inv)
    assert codes(reasons) == ["SUBTOTAL_MISMATCH"]
    assert "off by -5.00" in reasons[0].message


def test_total_mismatch_with_discount_and_tax() -> None:
    inv = make_invoice([("A", None, 10, "10.00")])
    inv = inv.model_copy(
        update={"discount": Decimal("5.00"), "tax": Decimal("9.50"), "total": Decimal("104.50")}
    )
    assert validate_arithmetic(inv) == []
    inv = inv.model_copy(update={"total": Decimal("114.50")})
    reasons = validate_arithmetic(inv)
    assert codes(reasons) == ["TOTAL_MISMATCH"]
    assert "discount" in reasons[0].message


def test_total_tolerance_is_configurable() -> None:
    inv = make_invoice([("A", None, 1, "10.00")])
    inv = inv.model_copy(update={"total": Decimal("10.05")})
    assert codes(validate_arithmetic(inv)) == ["TOTAL_MISMATCH"]
    loose = MatchPolicy(total_tolerance=Decimal("0.10"))
    assert validate_arithmetic(inv, loose) == []
