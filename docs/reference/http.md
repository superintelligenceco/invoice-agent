# HTTP API reference

Start the service with `invoice-agent serve` (needs the `[api]` extra) or the container image.
Interactive OpenAPI docs are at `/docs` on the running service.

| Endpoint | Body | Returns |
| --- | --- | --- |
| `GET /` | | The upload page: pick a PDF, see the fields, decision, and reasons |
| `GET /health` | | Status, version, extractor, PO count, invoices seen |
| `POST /extract` | multipart `file` (PDF, 20 MB max) | `Invoice` |
| `POST /process` | multipart `file` | `Result` with decision and reasons |
| `POST /match` | `Invoice` JSON | `Result`, for invoices extracted elsewhere |

```sh
curl -s -F "file=@dataset/invoices/016_b04.pdf" http://127.0.0.1:8000/process
```

The ledger lives in memory for the life of the process.
