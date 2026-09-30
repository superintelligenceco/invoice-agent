from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from invoice_agent.normalize import (
    detect_currency,
    normalize_doc_number,
    normalize_po,
    normalize_vendor,
    parse_amount,
    parse_date,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1.234,56 €", "1234.56"),
        ("$1,234.56", "1234.56"),
        ("£12.10", "12.10"),
        ("USD 99.00", "99.00"),
        ("(12.00)", "-12.00"),
        ("-5.25", "-5.25"),
        ("1,234", "1234"),
        ("12,5", "12.5"),
        ("1 234,56", "1234.56"),
        ("42", "42"),
    ],
)
def test_parse_amount(text: str, expected: str) -> None:
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", [None, "", "abc", "12.34.56x"])
def test_parse_amount_rejects_garbage(text: str | None) -> None:
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    ("text", "day_first", "expected"),
    [
        ("2026-03-14", False, dt.date(2026, 3, 14)),
        ("14.03.2026", False, dt.date(2026, 3, 14)),
        ("03/04/2026", False, dt.date(2026, 3, 4)),
        ("03/04/2026", True, dt.date(2026, 4, 3)),
        ("25/03/2026", False, dt.date(2026, 3, 25)),
        ("14 Mar 2026", False, dt.date(2026, 3, 14)),
        ("March 14, 2026", False, dt.date(2026, 3, 14)),
        ("Sept 1 2026", False, dt.date(2026, 9, 1)),
    ],
)
def test_parse_date(text: str, day_first: bool, expected: dt.date) -> None:
    assert parse_date(text, day_first=day_first) == expected


def test_parse_date_invalid() -> None:
    assert parse_date("31.02.2026") is None
    assert parse_date("no date here") is None


def test_detect_currency() -> None:
    assert detect_currency("Total 12.00 €") == "EUR"
    assert detect_currency("Amount due £5.00") == "GBP"
    assert detect_currency("ALL AMOUNTS IN USD") == "USD"
    assert detect_currency("Total 12.00") is None


def test_doc_number_normalization() -> None:
    assert normalize_doc_number("BF-2026/0401") == normalize_doc_number("BF 2026-0401")
    assert normalize_doc_number(None) == ""
    assert normalize_po("PO-2026-0101") == normalize_po("2026 0101")


def test_vendor_normalization_drops_legal_suffixes() -> None:
    assert normalize_vendor("Quillfeather Office Supply Co.") == "quillfeather office supply"
    assert normalize_vendor("The Example GmbH") == "example"
    assert normalize_vendor(None) == ""
