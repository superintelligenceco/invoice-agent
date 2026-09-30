from __future__ import annotations

import csv
from pathlib import Path

import pytest

from invoice_agent.data import (
    DataError,
    load_purchase_orders,
    load_receipts,
    po_to_rows,
    receipts_to_rows,
    write_sqlite,
)

from .conftest import DATASET


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_json_csv_and_sqlite_load_the_same_data(tmp_path: Path) -> None:
    pos = load_purchase_orders(DATASET / "purchase_orders.json")
    receipts = load_receipts(DATASET / "receipts.json")
    assert len(pos) == 44

    _write_csv(tmp_path / "pos.csv", po_to_rows(pos))
    _write_csv(tmp_path / "receipts.csv", receipts_to_rows(receipts))
    write_sqlite(tmp_path / "ap.db", pos, receipts)

    assert load_purchase_orders(tmp_path / "pos.csv") == pos
    assert load_receipts(tmp_path / "receipts.csv") == receipts
    assert load_purchase_orders(tmp_path / "ap.db") == pos
    assert load_receipts(tmp_path / "ap.db") == receipts


def test_example_csv_files_load() -> None:
    examples = DATASET.parent / "examples"
    pos = load_purchase_orders(examples / "purchase_orders.csv")
    assert pos[0].lines
    assert load_receipts(examples / "receipts.csv")


def test_unsupported_and_missing_files(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="unsupported"):
        load_purchase_orders(tmp_path / "pos.xlsx")
    with pytest.raises(DataError, match="not found"):
        load_receipts(tmp_path / "missing.db")
    (tmp_path / "bad.json").write_text("{}")
    with pytest.raises(DataError, match="JSON list"):
        load_purchase_orders(tmp_path / "bad.json")
