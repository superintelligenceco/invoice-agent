# Concepts

## Extractors

An extractor turns the text of a PDF into an `Invoice`. invoice-agent has two:

- `layout` (default): deterministic and offline. It knows label synonyms in English and German,
  US and European number formats, and several date formats. It was built against the five
  layouts in the dataset.
- `llm`: sends the PDF text to any server that implements the OpenAI `POST /chat/completions`
  API and validates the JSON answer against the schema. Configure it with
  `INVOICE_AGENT_LLM_BASE_URL`, `INVOICE_AGENT_LLM_MODEL`, and `INVOICE_AGENT_LLM_API_KEY`.

Pick one with `--extractor layout|llm`. Add `--ocr` to read pages without a text layer (needs the
`[ocr]` extra and the tesseract binary).

## Money

Every amount is a `decimal.Decimal`, from parsing to the JSON output. Amounts serialize as
strings, so `12.10` never becomes `12.1`. See [ADR 0001](adr/0001-decimal-money.md).

## Matching

The matcher runs these steps in order:

1. **Duplicates** against the ledger: the same vendor and invoice number rejects; the same
   currency and total within `duplicate_window_days` under another number needs review.
2. **Find the PO**: a printed PO number, or the best-fitting open PO of the vendor when none is
   printed.
3. **Vendor and currency** must agree with the PO.
4. **Line alignment**: equal SKUs pair first, then descriptions by similarity.
5. **Price**: a unit price above the PO price by more than the tolerance needs review.
6. **Quantity**: billed plus earlier billed quantity over ordered rejects; over received (3-way)
   needs review.

A PO with `receipt_required: true` gets a 3-way match against goods receipts. Services use
`receipt_required: false` and get a 2-way match.

## Reasons and decisions

Every finding is a `Reason` with a stable `code`, a `severity` (`info`, `review`, or `reject`),
a message that names the line and the numbers, and structured `data`. The decision is the
strictest severity among the reasons:

| Strictest severity | Decision |
| --- | --- |
| none or `info` | `auto_approve` |
| `review` | `needs_review` |
| `reject` | `reject` |

The full list of codes is in the
[README](https://github.com/superintelligenceco/invoice-agent#reason-codes).

## Ledger

The ledger remembers invoices already processed and the quantities billed per PO line. That is
how the matcher catches duplicates and overbilling across several invoices. The CLI keeps it in
memory for one run, or in a file with `--ledger`. The HTTP service keeps it in memory for the life
of the process. Order matters: process invoices in the order they arrive.

## Policy

Pass `--policy policy.json` to override any threshold:

| Setting | Default | Meaning |
| --- | --- | --- |
| `price_tolerance_pct` | `0.02` | Allowed unit-price increase over the PO, as a fraction |
| `price_tolerance_abs` | `0.05` | Allowed unit-price increase in currency units |
| `qty_tolerance_pct` | `0` | Allowed quantity over ordered or received, as a fraction |
| `line_rounding` | `0.02` | Per-line rounding difference reported as info only |
| `total_tolerance` | `0.02` | Allowed difference on subtotal and total checks |
| `vendor_match_threshold` | `85.0` | Minimum fuzzy score (0-100) for the vendor to equal the PO vendor |
| `line_match_threshold` | `0.55` | Minimum description similarity (0-1) to pair lines without a SKU |
| `duplicate_window_days` | `14` | Same vendor and total within this many days is a possible duplicate |
| `require_po_number` | `true` | Send invoices without a printed PO number to review |

## Eval

`invoice-agent eval` scores both halves of the pipeline on a labeled dataset. `--oracle` skips
extraction and feeds the ground truth to the matcher, so you can tell an extraction regression
from a rule regression.
