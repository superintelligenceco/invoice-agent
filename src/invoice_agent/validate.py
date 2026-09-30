"""Arithmetic checks: line amounts, subtotal, and total."""

from __future__ import annotations

from decimal import Decimal

from .normalize import quantize
from .policy import MatchPolicy
from .schema import Invoice, Reason, Severity


def validate_arithmetic(inv: Invoice, policy: MatchPolicy | None = None) -> list[Reason]:
    """Check that the numbers on the invoice add up.

    * each line: ``quantity * unit_price == amount`` (within ``line_rounding``)
    * ``sum(line amounts) == subtotal``
    * ``subtotal - discount + tax == total``

    Differences up to ``policy.line_rounding`` per line are reported as
    ``info`` so the reviewer can see them, without blocking approval.
    """
    policy = policy or MatchPolicy()
    reasons: list[Reason] = []
    for i, li in enumerate(inv.line_items, start=1):
        expected = quantize(li.quantity * li.unit_price)
        diff = abs(expected - li.amount)
        if diff == 0:
            continue
        data = {"line": i, "expected": str(expected), "printed": str(li.amount)}
        if diff <= policy.line_rounding:
            reasons.append(
                Reason(
                    code="LINE_ROUNDING",
                    severity=Severity.INFO,
                    message=f"Line {i}: {li.quantity} x {li.unit_price} = {expected}, "
                    f"invoice shows {li.amount} (rounding difference of {diff}).",
                    data=data,
                )
            )
        else:
            reasons.append(
                Reason(
                    code="LINE_AMOUNT_MISMATCH",
                    severity=Severity.REVIEW,
                    message=f"Line {i}: {li.quantity} x {li.unit_price} = {expected}, "
                    f"but the invoice shows {li.amount}.",
                    data=data,
                )
            )

    lines_sum = sum((li.amount for li in inv.line_items), Decimal("0"))
    if inv.subtotal is not None and inv.line_items:
        diff = abs(lines_sum - inv.subtotal)
        if diff > policy.total_tolerance:
            reasons.append(
                Reason(
                    code="SUBTOTAL_MISMATCH",
                    severity=Severity.REVIEW,
                    message=f"Line amounts sum to {lines_sum}, but the subtotal is {inv.subtotal} "
                    f"(off by {lines_sum - inv.subtotal:+}).",
                    data={"lines_sum": str(lines_sum), "subtotal": str(inv.subtotal)},
                )
            )

    if inv.total is not None:
        base = inv.subtotal if inv.subtotal is not None else lines_sum
        expected_total = base - inv.discount + (inv.tax or Decimal("0"))
        diff = abs(expected_total - inv.total)
        if diff > policy.total_tolerance:
            parts = f"{base}" + (f" - {inv.discount} discount" if inv.discount else "")
            parts += f" + {inv.tax or 0} tax"
            reasons.append(
                Reason(
                    code="TOTAL_MISMATCH",
                    severity=Severity.REVIEW,
                    message=f"{parts} = {expected_total}, but the total is {inv.total} "
                    f"(off by {inv.total - expected_total:+}).",
                    data={"expected": str(expected_total), "total": str(inv.total)},
                )
            )
    return reasons
