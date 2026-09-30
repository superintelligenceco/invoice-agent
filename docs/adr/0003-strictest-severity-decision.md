# 0003: The decision is the strictest severity among the reasons

- Status: accepted
- Date: 2026-09-30

## Context

An invoice can trip several checks at once: a rounding difference, a price variance, and an
overbilled quantity. The pipeline needs one decision that a person or a script can act on, and
the person needs to see every finding, not only the one that decided.

## Decision

Every check emits `Reason` objects with a code from `reasons.CODES` and a severity of `info`,
`review`, or `reject`. `pipeline.decide()` returns `reject` if any reason rejects, `needs_review`
if any reason needs review, and `auto_approve` otherwise. `info` reasons never block approval.

## Consequences

- Adding a rule means adding a code and a severity; the decision logic doesn't change.
- Results always list every reason, so a reviewer sees the full picture.
- Weighting or scoring reasons isn't possible without a new decision; tune thresholds in the
  policy instead.
