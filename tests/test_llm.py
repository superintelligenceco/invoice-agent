from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from invoice_agent.extract.llm import LLMExtractionError, LLMExtractor, parse_llm_json
from invoice_agent.ingest import Document

ANSWER = {
    "vendor": "Example Vendor Ltd",
    "invoice_number": "EV-1",
    "invoice_date": "2026-02-01",
    "currency": "EUR",
    "line_items": [
        {"description": "Thing", "quantity": "2", "unit_price": "1.50", "amount": "3.00"}
    ],
    "subtotal": "3.00",
    "discount": None,
    "tax": "0.57",
    "total": "3.57",
}


def _transport(
    content: str, status: int = 200, seen: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = {"choices": [{"message": {"content": content}}]}
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_llm_extractor_calls_chat_completions() -> None:
    seen: list[httpx.Request] = []
    ex = LLMExtractor(
        base_url="https://llm.invalid/v1/",
        api_key="test-key",
        model="some-model",
        transport=_transport(json.dumps(ANSWER), seen=seen),
    )
    inv = ex.extract(Document(source="a", pages=["Invoice EV-1 ..."]))
    assert inv.total == Decimal("3.57")
    assert inv.discount == Decimal("0")
    req = seen[0]
    assert str(req.url) == "https://llm.invalid/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(req.content)
    assert payload["model"] == "some-model"
    assert payload["temperature"] == 0
    assert "Invoice EV-1" in payload["messages"][1]["content"]


def test_llm_extractor_skips_empty_documents() -> None:
    ex = LLMExtractor(transport=_transport("unused"))
    assert ex.extract(Document(source="a", pages=[""])).vendor is None


def test_llm_http_error() -> None:
    ex = LLMExtractor(base_url="https://llm.invalid/v1", transport=_transport("{}", status=500))
    with pytest.raises(LLMExtractionError, match="HTTP 500"):
        ex.extract(Document(source="a", pages=["x"]))


def test_parse_llm_json_tolerates_code_fences() -> None:
    inv = parse_llm_json("```json\n" + json.dumps(ANSWER) + "\n```")
    assert inv.invoice_number == "EV-1"


@pytest.mark.parametrize("content", ["not json", json.dumps({"total": "abc"})])
def test_parse_llm_json_rejects_bad_output(content: str) -> None:
    with pytest.raises(LLMExtractionError):
        parse_llm_json(content)
