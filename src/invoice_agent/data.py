"""Load purchase orders and goods receipts from JSON, CSV or SQLite.

JSON files hold a list of objects shaped like :class:`PurchaseOrder` or
:class:`GoodsReceipt`. CSV files and SQLite tables hold one row per line:

* purchase orders: ``po_number, vendor, currency, receipt_required, line_no,
  sku, description, quantity, unit_price``
* receipts: ``receipt_id, po_number, date, line_no, quantity``

A SQLite database uses the tables ``po_lines`` and ``receipt_lines`` with the
same columns.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .schema import GoodsReceipt, PurchaseOrder

PO_COLUMNS = (
    "po_number",
    "vendor",
    "currency",
    "receipt_required",
    "line_no",
    "sku",
    "description",
    "quantity",
    "unit_price",
)
RECEIPT_COLUMNS = ("receipt_id", "po_number", "date", "line_no", "quantity")

_SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


class DataError(ValueError):
    pass


def load_purchase_orders(path: str | Path) -> list[PurchaseOrder]:
    """Load purchase orders from a ``.json``, ``.csv`` or SQLite file."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".json":
        return [PurchaseOrder.model_validate(o) for o in _json_list(p)]
    if suffix == ".csv":
        return po_from_rows(_csv_rows(p))
    if suffix in _SQLITE_SUFFIXES:
        return po_from_rows(_sqlite_rows(p, "po_lines", PO_COLUMNS))
    raise DataError(f"{p}: unsupported purchase order format {suffix!r}")


def load_receipts(path: str | Path) -> list[GoodsReceipt]:
    """Load goods receipts from a ``.json``, ``.csv`` or SQLite file."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".json":
        return [GoodsReceipt.model_validate(o) for o in _json_list(p)]
    if suffix == ".csv":
        return receipts_from_rows(_csv_rows(p))
    if suffix in _SQLITE_SUFFIXES:
        return receipts_from_rows(_sqlite_rows(p, "receipt_lines", RECEIPT_COLUMNS))
    raise DataError(f"{p}: unsupported receipt format {suffix!r}")


def po_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[PurchaseOrder]:
    """Group flat PO line rows into purchase orders, keeping first-seen order."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        number = str(row["po_number"]).strip()
        po = grouped.setdefault(
            number,
            {
                "po_number": number,
                "vendor": row["vendor"],
                "currency": row["currency"],
                "receipt_required": _bool(row.get("receipt_required", True)),
                "lines": [],
            },
        )
        po["lines"].append(
            {
                "line_no": int(row["line_no"]),
                "sku": row.get("sku") or None,
                "description": row["description"],
                "quantity": str(row["quantity"]),
                "unit_price": str(row["unit_price"]),
            }
        )
    return [PurchaseOrder.model_validate(po) for po in grouped.values()]


def receipts_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[GoodsReceipt]:
    """Group flat receipt line rows into goods receipts."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = str(row["receipt_id"]).strip()
        rec = grouped.setdefault(
            rid,
            {
                "receipt_id": rid,
                "po_number": row["po_number"],
                "date": row.get("date") or None,
                "lines": [],
            },
        )
        rec["lines"].append({"line_no": int(row["line_no"]), "quantity": str(row["quantity"])})
    return [GoodsReceipt.model_validate(r) for r in grouped.values()]


def po_to_rows(pos: Iterable[PurchaseOrder]) -> list[dict[str, Any]]:
    """Flatten purchase orders into CSV/SQLite rows."""
    return [
        {
            "po_number": po.po_number,
            "vendor": po.vendor,
            "currency": po.currency,
            "receipt_required": int(po.receipt_required),
            "line_no": line.line_no,
            "sku": line.sku or "",
            "description": line.description,
            "quantity": str(line.quantity),
            "unit_price": str(line.unit_price),
        }
        for po in pos
        for line in po.lines
    ]


def receipts_to_rows(receipts: Iterable[GoodsReceipt]) -> list[dict[str, Any]]:
    """Flatten goods receipts into CSV/SQLite rows."""
    return [
        {
            "receipt_id": r.receipt_id,
            "po_number": r.po_number,
            "date": r.date.isoformat() if r.date else "",
            "line_no": line.line_no,
            "quantity": str(line.quantity),
        }
        for r in receipts
        for line in r.lines
    ]


def write_sqlite(
    path: str | Path, pos: Iterable[PurchaseOrder], receipts: Iterable[GoodsReceipt]
) -> None:
    """Write purchase orders and receipts to a SQLite database."""
    with sqlite3.connect(path) as conn:
        for table, columns, rows in (
            ("po_lines", PO_COLUMNS, po_to_rows(pos)),
            ("receipt_lines", RECEIPT_COLUMNS, receipts_to_rows(receipts)),
        ):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"CREATE TABLE {table} ({', '.join(columns)})")
            conn.executemany(
                f"INSERT INTO {table} VALUES ({', '.join('?' for _ in columns)})",
                [tuple(r[c] for c in columns) for r in rows],
            )
    conn.close()


def _json_list(path: Path) -> list[Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise DataError(f"{path}: expected a JSON list")
    return data


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _sqlite_rows(path: Path, table: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    if not path.exists():
        raise DataError(f"{path}: database not found")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(f"SELECT {', '.join(columns)} FROM {table}")
        except sqlite3.OperationalError as exc:
            raise DataError(f"{path}: {exc}") from exc
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "n", ""}
