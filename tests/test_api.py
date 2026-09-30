from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from invoice_agent.api import create_app
from invoice_agent.data import load_purchase_orders, load_receipts

from .conftest import DATASET


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        load_purchase_orders(DATASET / "purchase_orders.json"),
        load_receipts(DATASET / "receipts.json"),
    )
    return TestClient(app)


def _upload(name: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, (DATASET / "invoices" / name).read_bytes(), "application/pdf")}


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["purchase_orders"] == 44
    assert body["extractor"] == "layout"


def test_extract(client: TestClient) -> None:
    resp = client.post("/extract", files=_upload("013_b01.pdf"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "EUR"
    assert body["total"] == "514.08"


def test_process_then_duplicate(client: TestClient) -> None:
    first = client.post("/process", files=_upload("001_q01.pdf")).json()
    assert first["decision"] == "auto_approve"
    assert first["match_type"] == "3-way"
    again = client.post("/process", files=_upload("001_q01.pdf")).json()
    assert again["decision"] == "reject"
    assert again["reasons"][0]["code"] == "DUPLICATE_INVOICE"
    assert client.get("/health").json()["invoices_seen"] == 2


def test_process_rejects_non_pdf(client: TestClient) -> None:
    resp = client.post("/process", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert resp.status_code == 422


def test_match_json_invoice(client: TestClient) -> None:
    extracted = client.post("/extract", files=_upload("016_b04.pdf")).json()
    result = client.post("/match", json=extracted).json()
    assert result["decision"] == "needs_review"
    assert [r["code"] for r in result["reasons"]] == ["PRICE_VARIANCE"]
