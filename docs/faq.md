# FAQ

## Does it need an API key or network access?

No. The default `layout` extractor and all matching rules run offline. Only the optional `llm`
extractor calls a server, and you can point it at a local one such as Ollama or vLLM.

## How accurate is it on my invoices?

The eval numbers measure the five layouts in the shipped dataset, which the layout extractor was
built against. They catch regressions; they don't predict accuracy on new vendors. Add your own
invoices to a dataset directory with a `manifest.json` and ground truth, then run
`invoice-agent eval --dataset DIR`. For layouts the rules don't cover, try `--extractor llm`.

## What happens with a scanned invoice?

A page without a text layer gets `NO_TEXT_LAYER` and the invoice goes to review instead of being
guessed. Install the `[ocr]` extra and tesseract, then pass `--ocr`.

## Why did an invoice I processed twice get rejected?

The ledger remembers every invoice it has seen. Processing the same invoice again is a
`DUPLICATE_INVOICE`. Use a fresh ledger (or restart the service) to start over.

## Can I change the tolerances?

Yes. Write a JSON file with the settings you want to change and pass `--policy FILE`. See
[Policy](concepts.md#policy).

## Which PO and receipt formats work?

JSON, CSV, and SQLite, picked by file extension. See the
[README](https://github.com/superintelligenceco/invoice-agent#po-and-receipt-data).

## Is the dataset real?

No. Every vendor, address, and product is fictional, and every page carries a footer that says it
is a synthetic test document. `invoice-agent generate-dataset` rebuilds it byte for byte.

## How do I verify a download?

Each release has a `SHA256SUMS` file and build provenance attestations. Run
`gh attestation verify invoice-agent-linux-x64 -R superintelligenceco/invoice-agent`. The image
is signed with cosign keyless signing; the release notes show the `cosign verify` command.
