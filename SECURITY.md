# Security policy

## Supported versions

Security fixes land on the latest minor release.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Report a vulnerability

Don't open a public issue for a security problem. Report it privately through
[GitHub private vulnerability reporting](https://github.com/superintelligenceco/invoice-agent/security/advisories/new).

Include the version, the command or request you sent, and the smallest synthetic PDF that
reproduces the problem. Don't send real invoices. You get an acknowledgment within 5 business
days. After the fix ships, the advisory is published with credit to you unless you ask otherwise.

## Trust model

invoice-agent parses untrusted PDFs. Treat it like any document parser:

- PDF parsing is done by pdfplumber (pdfminer.six) and pypdf. Keep them updated. Dependabot opens
  pull requests for new versions.
- The HTTP service has no authentication. Bind it to `127.0.0.1` (the default) or put it behind a
  proxy that authenticates. Uploads are capped at 20 MB.
- The `llm` extractor sends the invoice text to the endpoint in `INVOICE_AGENT_LLM_BASE_URL`. Point
  it at a provider you're allowed to share invoice data with, or at a local server. The API key is
  read from `INVOICE_AGENT_LLM_API_KEY` and never written to disk or to results.
- Model output is validated against the invoice schema, and matching never trusts it more than
  text extracted from the PDF: it still has to pass every arithmetic and matching rule.

In scope:

- A PDF that makes ingestion hang, exhaust memory, or run code.
- A way to make the pipeline auto-approve an invoice that breaks a rule it claims to check.
- Secrets or invoice data that leak into logs, results, or error messages.

A wrong extraction or a wrong decision on a normal invoice is a bug, not a vulnerability. Open a
regular issue for it.
