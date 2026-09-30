"""Property-based tests for the pure core: parsing, arithmetic checks, alignment, and decisions.

Set ``HYPOTHESIS_PROFILE=nightly`` to run many more examples per property.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from invoice_agent.match import align_lines, description_similarity, vendor_similarity
from invoice_agent.normalize import (
    normalize_doc_number,
    normalize_vendor,
    parse_amount,
    parse_date,
    quantize,
)
from invoice_agent.pipeline import decide
from invoice_agent.schema import Decision, Invoice, LineItem, POLine, Reason, Severity
from invoice_agent.validate import validate_arithmetic

money = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
quantities = st.integers(min_value=1, max_value=500).map(Decimal)
dates = st.dates(min_value=dt.date(1990, 1, 1), max_value=dt.date(2099, 12, 31))
words = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=10)
descriptions = st.lists(words, min_size=1, max_size=5).map(" ".join)


def _us(value: Decimal) -> str:
    return f"{value:,.2f}"


def _eu(value: Decimal) -> str:
    return _us(value).replace(",", "_").replace(".", ",").replace("_", ".")


@given(money)
def test_parse_amount_reads_us_format(value: Decimal) -> None:
    assert parse_amount(_us(value)) == value
    assert parse_amount(f"${_us(value)}") == value
    assert parse_amount(f"USD {_us(value)}") == value


@given(money)
def test_parse_amount_reads_european_format(value: Decimal) -> None:
    assert parse_amount(_eu(value)) == value
    assert parse_amount(f"{_eu(value)} €") == value


@given(money.filter(lambda v: v > 0))
def test_parse_amount_reads_negatives(value: Decimal) -> None:
    assert parse_amount(f"({_us(value)})") == -value
    assert parse_amount(f"-{_us(value)}") == -value


@given(st.decimals(allow_nan=False, allow_infinity=False, min_value=-(10**9), max_value=10**9))
def test_quantize_is_idempotent_and_within_half_a_cent(value: Decimal) -> None:
    q = quantize(value)
    assert quantize(q) == q
    assert abs(q - value) <= Decimal("0.005")


@given(dates)
def test_parse_date_round_trips_every_supported_format(day: dt.date) -> None:
    assert parse_date(day.isoformat()) == day
    assert parse_date(day.strftime("%d.%m.%Y")) == day
    assert parse_date(day.strftime("%d %b %Y")) == day
    assert parse_date(day.strftime("%B %d, %Y")) == day
    assert parse_date(day.strftime("%m/%d/%Y")) == day
    assert parse_date(day.strftime("%d/%m/%Y"), day_first=True) == day


@given(st.text())
def test_normalize_doc_number_is_idempotent_and_alphanumeric(value: str) -> None:
    n = normalize_doc_number(value)
    assert normalize_doc_number(n) == n
    assert all(c.isascii() and (c.isupper() or c.isdigit()) for c in n)


@given(st.text())
def test_normalize_vendor_is_idempotent(value: str) -> None:
    n = normalize_vendor(value)
    assert normalize_vendor(n) == n


@given(st.text(max_size=40), st.text(max_size=40))
def test_vendor_similarity_is_symmetric_and_bounded(a: str, b: str) -> None:
    score = vendor_similarity(a, b)
    assert score == vendor_similarity(b, a)
    assert 0.0 <= score <= 100.0


@given(descriptions)
def test_description_similarity_ignores_case_and_word_order(text: str) -> None:
    shuffled = " ".join(reversed(text.split())).upper()
    assert description_similarity(text, shuffled) == 1.0


line_items = st.builds(
    lambda desc, qty, price: LineItem(
        description=desc, quantity=qty, unit_price=price, amount=quantize(qty * price)
    ),
    descriptions,
    quantities,
    money.map(lambda v: v / 100),
)


@given(st.lists(line_items, min_size=1, max_size=20), money, money)
def test_consistent_invoice_has_no_arithmetic_findings(
    lines: list[LineItem], tax: Decimal, discount: Decimal
) -> None:
    subtotal = sum((li.amount for li in lines), Decimal("0"))
    discount = min(discount, subtotal)
    inv = Invoice(
        line_items=lines,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=subtotal - discount + tax,
    )
    assert validate_arithmetic(inv) == []


@given(
    st.lists(line_items, min_size=1, max_size=10),
    st.decimals(min_value=Decimal("0.03"), max_value=Decimal("1000"), places=2),
)
def test_total_off_by_more_than_tolerance_is_flagged(lines: list[LineItem], off: Decimal) -> None:
    subtotal = sum((li.amount for li in lines), Decimal("0"))
    inv = Invoice(line_items=lines, subtotal=subtotal, tax=Decimal("0"), total=subtotal + off)
    assert [r.code for r in validate_arithmetic(inv)] == ["TOTAL_MISMATCH"]


@given(
    st.lists(descriptions, min_size=0, max_size=8),
    st.lists(descriptions, min_size=0, max_size=8),
    st.floats(min_value=0.0, max_value=1.0),
)
def test_align_lines_pairs_one_to_one(
    inv_desc: list[str], po_desc: list[str], threshold: float
) -> None:
    lines = [
        LineItem(description=d, quantity=Decimal(1), unit_price=Decimal(1), amount=Decimal(1))
        for d in inv_desc
    ]
    po_lines = [
        POLine(line_no=i, description=d, quantity=Decimal(1), unit_price=Decimal(1))
        for i, d in enumerate(po_desc, start=1)
    ]
    matches = align_lines(lines, po_lines, threshold)
    assert [m.invoice_line for m in matches] == list(range(1, len(lines) + 1))
    paired = [m.po_line for m in matches if m.po_line is not None]
    assert len(paired) == len(set(paired))
    assert len(paired) <= min(len(lines), len(po_lines))
    assert all(m.score >= threshold for m in matches if m.po_line is not None)


reasons = st.builds(
    lambda sev: Reason(code="X", severity=sev, message="m"),
    st.sampled_from(list(Severity)),
)
_RANK = {Decision.AUTO_APPROVE: 0, Decision.NEEDS_REVIEW: 1, Decision.REJECT: 2}


@given(st.lists(reasons, max_size=10), st.randoms())
def test_decide_ignores_order(found: list[Reason], rnd: object) -> None:
    shuffled = list(found)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    assert decide(shuffled) == decide(found)


@given(st.lists(reasons, max_size=10), reasons)
def test_decide_never_gets_less_strict_with_more_reasons(
    found: list[Reason], extra: Reason
) -> None:
    assert _RANK[decide([*found, extra])] >= _RANK[decide(found)]
