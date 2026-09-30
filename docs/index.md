# invoice-agent

invoice-agent reads invoice PDFs, matches them to purchase orders and goods receipts, and returns
an auto-approve, needs-review, or reject decision with the reasons spelled out.

![invoice-agent processing three invoices and running the eval](assets/demo.gif)

It runs offline. It pulls structured data out of an invoice PDF, checks the arithmetic, finds the
purchase order, aligns every invoice line with a PO line, compares prices and quantities against
what was ordered and received, and catches duplicate submissions. Every decision comes with
human-readable reasons and stable reason codes, so a reviewer sees why an invoice stopped, and a
script can route it.

## Install

=== "pip"

    ```sh
    pip install invoice-agent            # CLI, layout and LLM extractors
    pip install "invoice-agent[api]"     # plus the web page and HTTP API
    ```

=== "Standalone executable"

    ```sh
    curl -fsSL https://raw.githubusercontent.com/superintelligenceco/invoice-agent/main/install.sh | sh
    ```

=== "Container"

    ```sh
    docker run --rm -p 8000:8000 ghcr.io/superintelligenceco/invoice-agent:latest
    ```

Then follow the [quickstart](quickstart.md).

## Where to go next

- [Quickstart](quickstart.md): process your first invoice and run the eval.
- [Concepts](concepts.md): extractors, matching, reasons, decisions, and the ledger.
- [Architecture](architecture.md): how the modules fit together.
- [Reference](reference/cli.md): the CLI, the HTTP API, and the Python API.
- [FAQ](faq.md) and [architecture decisions](adr/index.md).
