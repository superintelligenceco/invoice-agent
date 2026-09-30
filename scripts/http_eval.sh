#!/bin/sh
# Posts every invoice in dataset/manifest.json, in order, to a running invoice-agent service and
# checks each decision against the manifest. The service must be fresh, because its in-memory
# ledger drives the duplicate and overbilling checks.
#
#   scripts/http_eval.sh [BASE_URL]    # default: http://127.0.0.1:8000
set -eu

base="${1:-http://127.0.0.1:8000}"
total=0
wrong=0
for row in $(jq -r '.[] | "\(.file)=\(.expected_decision)"' dataset/manifest.json); do
  file="${row%%=*}"
  expected="${row#*=}"
  got=$(curl -fsS -F "file=@dataset/$file" "$base/process" | jq -r .decision)
  total=$((total + 1))
  if [ "$got" != "$expected" ]; then
    wrong=$((wrong + 1))
    echo "MISMATCH $file: expected $expected, got $got"
  fi
done
echo "$((total - wrong))/$total decisions match the manifest"
[ "$total" -gt 0 ] && [ "$wrong" -eq 0 ]
