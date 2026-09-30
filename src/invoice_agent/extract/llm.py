"""Optional extractor that calls an OpenAI-compatible chat completions API.

Configure it with environment variables or constructor arguments:

* ``INVOICE_AGENT_LLM_BASE_URL`` (default ``https://api.openai.com/v1``)
* ``INVOICE_AGENT_LLM_API_KEY``
* ``INVOICE_AGENT_LLM_MODEL`` (default ``gpt-4o-mini``)

Any server that implements ``POST /chat/completions`` works, including local
ones such as vLLM, llama.cpp server or Ollama's OpenAI endpoint.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from ..ingest import Document
from ..schema import Invoice

SYSTEM_PROMPT = """You extract data from supplier invoices for an accounts payable team.
Return one JSON object that matches the JSON schema below. Rules:
- Copy values exactly as printed. Do not correct arithmetic errors.
- Amounts are decimal strings with a dot separator and no currency symbol, e.g. "1234.50".
- Dates are ISO 8601 (YYYY-MM-DD).
- currency is the ISO 4217 code.
- discount is a positive number, or "0" when there is none.
- subtotal is the sum of line amounts before discount and tax, as printed.
- Use null for anything that is not on the document.
Return JSON only, with no commentary.

JSON schema:
"""


class LLMExtractionError(RuntimeError):
    pass


@dataclass
class LLMExtractor:
    """Extractor backed by any OpenAI-compatible ``/chat/completions`` endpoint."""

    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "INVOICE_AGENT_LLM_BASE_URL", "https://api.openai.com/v1"
        )
    )
    api_key: str | None = field(default_factory=lambda: os.environ.get("INVOICE_AGENT_LLM_API_KEY"))
    model: str = field(
        default_factory=lambda: os.environ.get("INVOICE_AGENT_LLM_MODEL", "gpt-4o-mini")
    )
    timeout: float = 60.0
    max_chars: int = 24_000
    transport: httpx.BaseTransport | None = None
    name: str = "llm"

    def extract(self, doc: Document) -> Invoice:
        if not doc.has_text:
            return Invoice()
        payload = self._payload(doc.text[: self.max_chars])
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            resp = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
            )
        if resp.status_code >= 400:
            raise LLMExtractionError(
                f"LLM endpoint returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMExtractionError("unexpected response shape from LLM endpoint") from exc
        return parse_llm_json(content)

    def _payload(self, text: str) -> dict[str, Any]:
        schema = json.dumps(Invoice.model_json_schema(), separators=(",", ":"))
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + schema},
                {"role": "user", "content": f"Invoice text:\n\n{text}"},
            ],
        }


def parse_llm_json(content: str) -> Invoice:
    """Parse model output into an :class:`Invoice`, tolerating code fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMExtractionError(f"model did not return JSON: {content[:120]!r}") from exc
    if isinstance(data, dict) and data.get("discount") is None:
        data["discount"] = "0"
    try:
        return Invoice.model_validate(data)
    except ValidationError as exc:
        raise LLMExtractionError(f"model output failed schema validation: {exc}") from exc
