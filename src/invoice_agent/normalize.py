"""Parsing helpers for amounts, dates, currencies and identifiers."""

from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")

CURRENCY_SYMBOLS: dict[str, str] = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
ISO_CURRENCIES = ("USD", "EUR", "GBP", "CHF", "CAD", "AUD", "JPY", "SEK", "NOK", "DKK")

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}

AMOUNT_RE = r"\(?-?(?:[$€£¥]\s?)?-?\d{1,3}(?:[.,  ]\d{3})*(?:[.,]\d{1,4})?\)?(?:\s?[€$£])?"


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(text: str | None) -> Decimal | None:
    """Parse ``1,234.56``, ``1.234,56 €``, ``(12.00)``, ``USD 99`` and similar.

    The decimal separator is whichever of ``.`` or ``,`` appears last and is
    followed by one to four digits at the end of the string.
    """
    if text is None:
        return None
    s = text.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[()\s  $€£¥]", "", s)
    s = re.sub(r"^(?:[A-Z]{3})|(?:[A-Z]{3})$", "", s)
    if s.startswith("-"):
        negative = True
        s = s[1:]
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    sep = "." if last_dot > last_comma else ","
    idx = max(last_dot, last_comma)
    if (
        idx != -1
        and 1 <= len(s) - idx - 1 <= 4
        and not (
            # "1,234" with a comma and exactly three digits is a thousands group.
            sep == ","
            and len(s) - idx - 1 == 3
            and s.count(",") >= 1
            and "." not in s
            and _looks_grouped(s)
        )
    ):
        whole, frac = s[:idx], s[idx + 1 :]
    else:
        whole, frac = s, ""
    whole = whole.replace(".", "").replace(",", "")
    try:
        value = Decimal(f"{whole}.{frac}" if frac else whole)
    except InvalidOperation:
        return None
    return -value if negative else value


def _looks_grouped(s: str) -> bool:
    return re.fullmatch(r"\d{1,3}(,\d{3})+", s) is not None


def detect_currency(text: str) -> str | None:
    """Return the most frequent ISO code or symbol found in ``text``."""
    counts: dict[str, int] = {}
    for code in ISO_CURRENCIES:
        n = len(re.findall(rf"\b{code}\b", text))
        if n:
            counts[code] = counts.get(code, 0) + n * 2
    for sym, code in CURRENCY_SYMBOLS.items():
        n = text.count(sym)
        if n:
            counts[code] = counts.get(code, 0) + n
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def parse_date(text: str | None, *, day_first: bool = False) -> dt.date | None:
    """Parse common invoice date formats.

    Supports ``2026-03-14``, ``14.03.2026``, ``03/14/2026`` (or ``14/03/2026``
    when ``day_first``), ``14 Mar 2026`` and ``March 14, 2026``.
    """
    if not text:
        return None
    s = text.strip().rstrip(".,")
    try:
        if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s):
            return dt.date(int(m[3]), int(m[2]), int(m[1]))
        if m := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
            a, b = int(m[1]), int(m[2])
            day, month = (a, b) if day_first else (b, a)
            if month > 12:
                day, month = month, day
            return dt.date(int(m[3]), month, day)
        if m := re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})", s):
            named = _MONTHS.get(m[2].lower())
            if named:
                return dt.date(int(m[3]), named, int(m[1]))
        if m := re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s):
            named = _MONTHS.get(m[1].lower())
            if named:
                return dt.date(int(m[3]), named, int(m[2]))
    except ValueError:
        return None
    return None


def normalize_doc_number(value: str | None) -> str:
    """Canonical form of an invoice or PO number: uppercase alphanumerics only.

    ``inv-001 042`` and ``INV001042`` both become ``INV001042``.
    """
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalize_po(value: str | None) -> str:
    """Canonical PO number. Drops a leading ``PO`` so ``PO-2026-0101`` equals ``2026-0101``."""
    n = normalize_doc_number(value)
    return n[2:] if n.startswith("PO") else n


_VENDOR_NOISE = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|gmbh|co|company|corp|corporation|plc|sa|ag|the)\b\.?",
    re.IGNORECASE,
)


def normalize_vendor(name: str | None) -> str:
    if not name:
        return ""
    s = _VENDOR_NOISE.sub(" ", name.lower())
    s = re.sub(r"[^a-z0-9& ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
