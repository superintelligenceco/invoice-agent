# 0002: A deterministic offline extractor is the default

- Status: accepted
- Date: 2026-09-30

## Context

Extraction can use rules over the PDF text or a language model. A model handles unseen layouts
better but costs money per invoice, needs network access or a local server, and isn't
deterministic, which makes regressions hard to see in an eval.

## Decision

The default extractor, `layout`, is rule-based and offline: label synonyms, number and date
formats, and table parsing over the text layer. An `llm` extractor that calls any
OpenAI-compatible endpoint is available behind the same `Extractor` interface. Tests mock that
endpoint with `httpx.MockTransport` and never call a paid API.

## Consequences

- `invoice-agent eval` is reproducible, so CI can require 100% decision accuracy on the shipped
  dataset.
- The layout extractor needs new label synonyms for new vendors; the docs say so next to the
  eval numbers.
- Users who want model-based extraction opt in with `--extractor llm` and can use a local model.
