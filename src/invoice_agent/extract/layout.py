"""Deterministic, offline extractor based on labels and table-row patterns.

It needs no network and no model. It reads the PDF text layer line by line:

* header fields come from label synonyms (``Invoice No``, ``INV NO.``,
  ``Rechnungsnr.``, ``Your order ref`` and so on),
* line items come from rows between a table header and the totals block,
  with wrapped descriptions folded back into the row above,
* totals come from the last amount on each totals line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..ingest import Document
from ..normalize import detect_currency, parse_amount, parse_date
from ..schema import Invoice, LineItem

_AMT = r"-?(?:[$€£]\s?)?\d{1,3}(?:[.,]\d{3})*[.,]\d{2,4}(?:\s?[€$£])?"
_TOTAL_AMT = re.compile(
    r"\(?-?(?:[A-Z]{3}\s)?(?:[$€£]\s?)?-?\d{1,3}(?:[.,  ]\d{3})*[.,]\d{2}\)?"
    r"(?:\s?[€$£]|\s[A-Z]{3})?"
)

_ITEM = re.compile(
    rf"""^
    (?:(?P<pos>\d{{1,3}})\s+(?=[A-Z]{{2,5}}-))?
    (?:(?P<sku>[A-Z]{{2,5}}-[A-Z0-9]{{2,}}(?:-[A-Z0-9]+)*)\s+)?
    (?P<desc>.+?)\s+
    (?P<qty>\d+(?:[.,]\d+)?)\s+
    (?:(?P<unit>[A-Za-z]{{1,8}})\s+)?
    (?P<price>{_AMT})\s+
    (?P<amount>{_AMT})
    $""",
    re.VERBOSE,
)

_QTY_WORDS = re.compile(r"\b(qty|quantity|menge|hours|hrs|units?)\b", re.I)
_AMOUNT_WORDS = re.compile(r"\b(amount|betrag|line total|ext\.? price|total)\b", re.I)

_FIELD_LABELS: dict[str, re.Pattern[str]] = {
    "invoice_number": re.compile(
        r"(?:rechnungsnr\.?\s*/\s*)?(?:invoice\s*(?:no\.?|number|num\.?|#)|inv\.?\s*no\.?|"
        r"rechnungsnr\.?)\s*[:#]?\s*(?P<v>.+)$",
        re.I,
    ),
    "invoice_date": re.compile(
        r"(?:invoice\s*date|date\s*of\s*issue|inv\.?\s*date|issue\s*date|issued|"
        r"datum\s*/\s*date|datum)\s*:?\s*(?P<v>.+)$",
        re.I,
    ),
    "due_date": re.compile(
        r"(?:due\s*date|payment\s*due|terms\s*due|fällig\s*/\s*due|fällig|\bdue)\s*:?\s*(?P<v>.+)$",
        re.I,
    ),
    "po_number": re.compile(
        r"(?:cust(?:omer)?\.?\s*po\s*#?|bestellnr\.?\s*/\s*po|your\s*order\s*ref(?:erence)?|"
        r"purchase\s*order(?:\s*(?:no\.?|number|#))?|p\.?o\.?\s*(?:number|no\.?|#))"
        r"\s*[:#]?\s*(?P<v>\S*\d\S*)",
        re.I,
    ),
}

_TOTALS: list[tuple[str, re.Pattern[str]]] = [
    (
        "subtotal",
        re.compile(r"^(?:sub\s*-?\s*total|zwischensumme|net(?:\s+(?:amount|total))?\b)", re.I),
    ),
    ("discount", re.compile(r"^(?:less\b.*discount|discount|rabatt|nachlass)", re.I)),
    ("tax", re.compile(r"^(?:sales\s*tax|tax|vat|mwst|gst|ust)\b", re.I)),
    (
        "total",
        re.compile(
            r"^(?:total|amount\s*due|balance\s*due|gesamtbetrag|invoice\s*total|grand\s*total)\b",
            re.I,
        ),
    ),
]

_TITLE = re.compile(r"\b(tax\s+invoice|rechnung\s*/\s*invoice|rechnung|invoice)\b\s*$", re.I)
_COMPANY = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|co|company|corp|plc|ag|sa|s\.a\.|bv|oy)\b\.?", re.I
)
_NOISE = (
    re.compile(r"page\s+\d+\s+of\s+\d+", re.I),
    re.compile(r"continued on next page", re.I),
)
_BILL_TO = re.compile(r"\b(bill\s*to|sold\s*to|invoice\s*to|rechnungsempfänger)\b", re.I)


@dataclass
class LayoutExtractor:
    """Offline extractor. See the module docstring for the approach."""

    name: str = "layout"

    def extract(self, doc: Document) -> Invoice:
        lines = _clean_lines(doc.text)
        if not lines:
            return Invoice()
        text = "\n".join(lines)
        currency = detect_currency(text)
        day_first = currency not in (None, "USD")
        fields: dict[str, object] = {"currency": currency}

        number = _first_value(lines, "invoice_number")
        if number:
            fields["invoice_number"] = _clean_number(number)
        for key in ("invoice_date", "due_date"):
            for value in _all_values(lines, key):
                parsed = parse_date(value, day_first=day_first)
                if parsed:
                    fields[key] = parsed
                    break
        po = _first_value(lines, "po_number")
        if po:
            fields["po_number"] = po.strip(".,;")
        fields["vendor"] = _vendor(lines)
        fields.update(_totals(lines))
        fields["line_items"] = _line_items(lines)
        return Invoice.model_validate(fields)


def _clean_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.replace(" ", " ").strip()
        if "Synthetic test document" in line or "Not a real invoice" in line:
            line = _NOISE[0].sub("", line.split("Synthetic test document")[0]).strip()
        for pattern in _NOISE:
            line = pattern.sub("", line).strip()
        line = re.sub(r"\s{2,}", " ", line)
        if line:
            out.append(line)
    return out


def _all_values(lines: list[str], key: str) -> list[str]:
    values = []
    for line in lines:
        for m in _FIELD_LABELS[key].finditer(line):
            values.append(m.group("v").strip())
    return values


def _first_value(lines: list[str], key: str) -> str | None:
    values = _all_values(lines, key)
    return values[0] if values else None


def _clean_number(value: str) -> str:
    value = re.sub(r"\(continued\)", "", value, flags=re.I).strip()
    # A number is at most two tokens ("HFP 778101"); drop anything after that.
    tokens = value.split()
    if len(tokens) >= 2 and tokens[1][:1].isdigit() and tokens[0].isalpha():
        return f"{tokens[0]} {tokens[1]}"
    return tokens[0] if tokens else value


def _vendor(lines: list[str]) -> str | None:
    header: list[str] = []
    for line in lines[:12]:
        if _BILL_TO.search(line) or _FIELD_LABELS["invoice_number"].search(line):
            break
        stripped = _TITLE.sub("", line).strip(" -|/")
        if stripped and not stripped[0].isdigit():
            header.append(stripped)
    for line in header:
        if _COMPANY.search(line):
            return line
    return header[0] if header else None


def _totals(lines: list[str]) -> dict[str, Decimal]:
    found: dict[str, Decimal] = {}
    for line in lines:
        for key, pattern in _TOTALS:
            if key in found or not pattern.search(line):
                continue
            amounts = _TOTAL_AMT.findall(line[pattern.search(line).end() :])  # type: ignore[union-attr]
            if not amounts:
                continue
            value = parse_amount(amounts[-1])
            if value is None:
                continue
            found[key] = abs(value) if key == "discount" else value
            break
    return found


def _is_header(line: str) -> bool:
    return bool(_QTY_WORDS.search(line) and _AMOUNT_WORDS.search(line)) and not re.search(
        r"\d+[.,]\d{2}", line
    )


def _is_totals(line: str) -> bool:
    return any(p.search(line) for _, p in _TOTALS)


def _line_items(lines: list[str]) -> list[LineItem]:
    items: list[LineItem] = []
    in_table = False
    for line in lines:
        if _is_header(line):
            in_table = True
            continue
        if not in_table:
            continue
        if _is_totals(line) or line.lower().startswith("payment terms"):
            in_table = False
            continue
        m = _ITEM.match(line)
        if m:
            qty = parse_amount(m["qty"]) if "," in m["qty"] else Decimal(m["qty"])
            price = parse_amount(m["price"])
            amount = parse_amount(m["amount"])
            if qty is None or price is None or amount is None:
                continue
            items.append(
                LineItem(
                    description=m["desc"].strip(),
                    sku=m["sku"],
                    quantity=qty,
                    unit_price=price,
                    amount=amount,
                )
            )
        elif items and not re.search(r"\d+[.,]\d{2}\b", line) and "(continued)" not in line:
            last = items[-1]
            items[-1] = last.model_copy(update={"description": f"{last.description} {line}"})
    return items
