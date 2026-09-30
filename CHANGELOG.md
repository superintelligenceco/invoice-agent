# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-09-30

invoice-agent now ships as a package on PyPI, standalone executables, and a signed multi-arch
container image, with a documentation site.

### Added

- The package on PyPI: `pip install invoice-agent`.
- An installer: `curl -fsSL https://raw.githubusercontent.com/superintelligenceco/invoice-agent/main/install.sh | sh`
  downloads the executable for your OS and CPU and checks it against `SHA256SUMS`.
- A documentation site at https://superintelligenceco.github.io/invoice-agent/ with a
  quickstart, concepts, an architecture diagram, CLI, HTTP, and Python API reference, an FAQ,
  and architecture decision records.
- `compose.yaml`: `docker compose up --build` runs the web page and API.
- SPDX SBOMs for the source tree and the image, build provenance attestations for every release
  file and the image, and a keyless cosign signature on the image.
- A web page at `/` of the HTTP service: upload an invoice PDF and see the extracted fields, the
  line matches, and the decision with its reasons. It is a single static file with no new
  dependencies.
- Standalone `invoice-agent` executables for linux-x64, linux-arm64, macos-arm64, and
  windows-x64, with a `SHA256SUMS` file, attached to each GitHub Release.
- A `linux/amd64` and `linux/arm64` image on `ghcr.io/superintelligenceco/invoice-agent`, tagged
  `vX.Y.Z` and `latest` on releases and `edge` on manual builds.
- The wheel and sdist attached to each GitHub Release.
- A Ship workflow that builds and smoke-tests all of the above when you push a `v*` tag.
- Development setup: a Makefile, pre-commit hooks, a dev container with a Codespaces badge, VS
  Code settings, `CITATION.cff`, and `llms.txt`.
- Tests: property-based tests of parsing, arithmetic, alignment, and decisions; a test that runs
  every command in the README and compares the output; benchmarks that fail CI above 2x the
  committed baseline; weekly mutation testing of the pure core; and a nightly run that posts
  every shipped invoice to the container over HTTP.
- Workflows: OpenSSF Scorecard, dependency review, actionlint, a Markdown link check, and Trivy
  scanning of the image.

### Changed

- Releases come only from pushed `v*` tags. release-please is gone.

### Fixed

- Vendor names now drop a legal suffix such as `Co` or `Ltd` even when a non-ASCII character
  touches it, so normalizing a name twice gives the same result. A property-based test found
  this.
- CodeQL no longer fails on a private repository without code scanning. It keeps the SARIF
  results as a run artifact instead.

## [0.1.0] - 2026-09-30

The first release. invoice-agent extracts invoice PDFs, matches them against purchase orders and
goods receipts, and returns an auto-approve, needs-review, or reject decision with the reasons.

### Added

- PDF ingestion through pdfplumber with a pypdf fallback, and optional OCR for pages without a
  text layer (`[ocr]` extra).
- A strict Pydantic invoice schema with `Decimal` money that serializes without losing trailing
  zeros.
- The offline `layout` extractor: label synonyms in English and German, US and European number
  and date formats, currency symbols and ISO codes, wrapped descriptions, discounts, and
  multi-page tables.
- The optional `llm` extractor for any OpenAI-compatible `/chat/completions` endpoint, with
  schema-validated output.
- Arithmetic validation of line amounts, subtotal, discount, tax, and total, with a rounding
  allowance reported as info.
- Matching: fuzzy vendor matching, PO lookup with or without the `PO` prefix, PO inference when
  no number is printed, SKU-then-description line alignment, price tolerances (percent or
  absolute), ordered and received quantity checks for 2-way and 3-way matches, partial receipts,
  cumulative billing across invoices, and duplicate and possible-duplicate detection.
- 18 stable reason codes with severities, and a tunable `MatchPolicy` loaded from JSON.
- A ledger that persists seen invoices and billed quantities across CLI runs.
- PO and receipt loaders for JSON, CSV, and SQLite.
- The `invoice-agent` CLI with `extract`, `process`, `eval`, `generate-dataset`, and `serve`.
- A FastAPI service with `/health`, `/extract`, `/process`, and `/match`, and a Dockerfile.
- A deterministic synthetic dataset: 50 invoices in five fictional vendor layouts, 44 POs, 36
  receipts, and ground truth with expected decisions and reason codes.
- `invoice-agent eval`: field-level extraction accuracy, decision accuracy, PO link accuracy,
  exception and reject precision and recall, reason code precision and recall, a confusion
  matrix, and an `--oracle` mode that scores matching with ground-truth extraction.
- CI on Python 3.11 to 3.13 on Linux and macOS, CodeQL, an eval workflow that posts results to
  the job summary, and release-please.

### Eval on the shipped dataset (layout extractor)

- Field accuracy 98.0% on header fields (100.0% on discount) and 99.2% per line item. The only miss is the
  scanned invoice without a text layer, which the pipeline routes to review.
- Decision accuracy, PO link accuracy, exception and reject precision and recall, and reason code
  precision and recall are all 100.0% on the 50 invoices.

[Unreleased]: https://github.com/superintelligenceco/invoice-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/superintelligenceco/invoice-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/superintelligenceco/invoice-agent/releases/tag/v0.1.0
