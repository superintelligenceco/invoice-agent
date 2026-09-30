# Contributing to invoice-agent

Thanks for helping. This guide shows you how to set up the project, add a matching rule or an
invoice layout, and open a pull request.

## Set up

You need Python 3.11 or later.

```sh
git clone https://github.com/superintelligenceco/invoice-agent.git
cd invoice-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Every test runs offline. The LLM extractor tests use `httpx.MockTransport`. Never add a test that
calls a paid API, and never commit a real invoice.

## Project layout

| Path | Contents |
| --- | --- |
| `src/invoice_agent/schema.py` | Pydantic models: `Invoice`, `PurchaseOrder`, `GoodsReceipt`, `Result`, `Reason`. |
| `src/invoice_agent/ingest.py` | PDF text layer through pdfplumber and pypdf, optional OCR. |
| `src/invoice_agent/extract/` | The `layout` (offline) and `llm` (OpenAI-compatible) extractors. |
| `src/invoice_agent/normalize.py` | Amount, date, currency, vendor, and document-number parsing. |
| `src/invoice_agent/validate.py` | Arithmetic checks. |
| `src/invoice_agent/match.py` | Duplicate detection, PO lookup and inference, line alignment, price and quantity checks, the ledger. |
| `src/invoice_agent/reasons.py` | The reason code catalog with severities. |
| `src/invoice_agent/pipeline.py` | Ties the stages together and makes the decision. |
| `src/invoice_agent/evaluate.py` | Scoring for `invoice-agent eval`. |
| `src/invoice_agent/synth/` | The synthetic dataset generator. |
| `src/invoice_agent/api.py`, `cli.py` | The HTTP service and the command line. |
| `dataset/` | Generated invoices, ground truth, POs, and receipts. |

## Checks

Run these before you push. CI runs the same commands on Python 3.11, 3.12, and 3.13, on Linux and
macOS.

```sh
ruff check .
ruff format --check .
mypy
pytest --cov
invoice-agent eval --min-decision-accuracy 1
```

To fix formatting and safe lint issues automatically, run `ruff format . && ruff check --fix .`.

## Add a matching rule

1. Add the code to `CODES` in `reasons.py` with its severity and a one-line meaning.
2. Emit it from `match.py` or `validate.py` with `reason(code, message, **data)`. Write the message
   for an AP clerk: name the line, the numbers, and the limit that was crossed.
3. Add tests in `tests/test_match.py` for the case that triggers it and the closest case that
   doesn't.
4. Add a case to the dataset (next section) and add the code to the reason table in `README.md`.

## Add an invoice layout or a dataset case

1. Add a fictional vendor to `synth/catalog.py`. Use names that can't be mistaken for a real
   company and addresses that don't exist.
2. Add invoices to `build()` in `synth/generate.py` with the expected decision and reason codes.
   Append new cases at the end so existing file names stay stable.
3. Run `invoice-agent generate-dataset dataset` and commit the result.
4. Run `invoice-agent eval`. If the layout extractor misses fields, extend its label synonyms in
   `extract/layout.py`, and add a focused test in `tests/test_extract.py`.

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and PR
  titles, for example `feat(match): flag invoices dated before the PO`. The release workflow builds
  the changelog from them.
- Keep each pull request focused on one change.
- Update `CHANGELOG.md` under `Unreleased` when behavior changes.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree
to uphold it.
