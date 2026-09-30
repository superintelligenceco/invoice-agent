# Quickstart

This page takes you from nothing to a processed invoice in a few minutes. You don't need an API
key or network access after the install.

## Install

Pick one:

```sh
pip install "invoice-agent[api]"
```

```sh
curl -fsSL https://raw.githubusercontent.com/superintelligenceco/invoice-agent/main/install.sh | sh
```

The installer downloads the standalone executable for your OS and CPU from the latest GitHub
Release, checks it against `SHA256SUMS`, and puts it in `~/.local/bin`. Set
`INVOICE_AGENT_VERSION=v0.2.0` to pin a version, or `INVOICE_AGENT_INSTALL_DIR` to change the
target directory.

## Get the sample data

The repository ships 50 synthetic invoices with purchase orders and receipts:

```sh
git clone https://github.com/superintelligenceco/invoice-agent.git
cd invoice-agent
```

## Process invoices

```sh
invoice-agent process dataset/invoices/016_b04.pdf dataset/invoices/005_q05.pdf \
  --pos dataset/purchase_orders.json --receipts dataset/receipts.json
```

```text
016_b04.pdf: NEEDS REVIEW
  vendor  Brightforge Maschinenteile GmbH
  invoice BF-2026/0404
  date    2026-03-17
  total   EUR 409.05
  po      PO-2026-0114 (3-way)
  lines   2/2 matched to PO lines
  [!] PRICE_VARIANCE: Line 1 ('Zahnriemen HTD 8M / Timing belt HTD 8M', PO line 1): unit price 61.56 is 8.0% above the PO price 57.00 (tolerance 2.0% or 0.05).
005_q05.pdf: NEEDS REVIEW
  ...
```

Add `--json` for one JSON result per line, and `--ledger ledger.json` to keep duplicate and
billed-quantity history across runs.

## Score the pipeline

```sh
invoice-agent eval
```

`eval` runs all 50 invoices through the pipeline in submission order and prints field accuracy,
decision accuracy, exception precision and recall, and a confusion matrix.

## Run the web page and API

```sh
docker compose up --build
```

Open <http://localhost:8000>, upload a PDF from `dataset/invoices/`, and see the extracted
fields, the line matches, and the decision. Without Docker, run
`invoice-agent serve --pos dataset/purchase_orders.json --receipts dataset/receipts.json`.

## Use your own data

Pass your own POs and receipts as JSON, CSV, or SQLite. The formats are in the
[README](https://github.com/superintelligenceco/invoice-agent#po-and-receipt-data). To change
tolerances, pass `--policy policy.json`; see [Concepts](concepts.md#policy).
