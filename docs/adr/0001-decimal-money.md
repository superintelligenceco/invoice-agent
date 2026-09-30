# 0001: Money is Decimal end to end

- Status: accepted
- Date: 2026-09-30

## Context

Matching compares printed totals, line amounts, and unit prices to the cent. Binary floats can't
represent most decimal amounts exactly, so `0.1 + 0.2 != 0.3`, and a float amount serialized to
JSON loses trailing zeros (`12.10` becomes `12.1`). Either one produces false mismatches or
misleading output.

## Decision

Every amount is a `decimal.Decimal`: parsing in `normalize.py`, the Pydantic models in
`schema.py`, the arithmetic checks, the matcher, and the JSON output, where amounts serialize as
strings. Code never converts an amount to `float`. Tolerances in `MatchPolicy` are `Decimal` too.

## Consequences

- Arithmetic checks are exact, and the tolerance settings mean what they say.
- JSON consumers get strings for amounts and must parse them as decimals.
- Property-based tests check that parsing a formatted amount gives back the same `Decimal`.
