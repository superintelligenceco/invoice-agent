#!/usr/bin/env sh
# Start the service first, from the repository root:
#   invoice-agent serve --pos dataset/purchase_orders.json --receipts dataset/receipts.json
set -eu
BASE="${BASE:-http://127.0.0.1:8000}"

curl -s "$BASE/health"
echo
curl -s -F "file=@dataset/invoices/016_b04.pdf" "$BASE/process"
echo
