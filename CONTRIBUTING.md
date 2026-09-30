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
| `src/invoice_agent/api.py`, `ui.html`, `cli.py` | The HTTP service, its upload page, and the command line. |
| `packaging/entry.py` | The entry point for the PyInstaller executables. |
| `dataset/` | Generated invoices, ground truth, POs, and receipts. |

## Checks

Run these before you push, or run `make lint typecheck test eval`. CI runs the same commands on
Python 3.11, 3.12, and 3.13, on Linux and macOS. `make help` lists every task, and
`pre-commit install` runs the linters on each commit.

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
  titles, for example `feat(match): flag invoices dated before the PO`.
- Keep each pull request focused on one change.
- Update `CHANGELOG.md` under `Unreleased` when behavior changes.

## Releases and downloadable artifacts

A maintainer releases by bumping the version in `pyproject.toml` and
`src/invoice_agent/__init__.py`, moving the `Unreleased` notes in `CHANGELOG.md` under the new
version, and pushing an annotated `vX.Y.Z` tag. The tag starts the
[Ship workflow](.github/workflows/ship.yml), which creates the GitHub Release and attaches the
files.

The Ship workflow builds and smoke-tests:

- the wheel and sdist,
- PyInstaller executables for linux-x64, linux-arm64, macos-arm64, and windows-x64, and a
  `SHA256SUMS` file,
- the `linux/amd64` and `linux/arm64` image on `ghcr.io/superintelligenceco/invoice-agent`.

On a tag it attaches the files to the GitHub Release and tags the image `vX.Y.Z` and `latest`.
To test the pipeline without releasing, run it by hand:

```sh
gh workflow run ship.yml --ref main
```

A manual run uploads the files as run artifacts and tags the image `edge`.

To build the executable locally:

```sh
pip install ".[api]" pyinstaller
pyinstaller --onefile --name invoice-agent --collect-data invoice_agent --collect-data pdfminer \
  --collect-submodules uvicorn packaging/entry.py
./dist/invoice-agent process dataset/invoices/001_q01.pdf --pos dataset/purchase_orders.json
```

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree
to uphold it.
