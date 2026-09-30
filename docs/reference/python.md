# Python API reference

```python
from invoice_agent.data import load_purchase_orders, load_receipts
from invoice_agent.pipeline import Pipeline

pipeline = Pipeline(load_purchase_orders("pos.csv"), load_receipts("receipts.csv"))
result = pipeline.process_pdf("invoice.pdf")
print(result.decision, [r.code for r in result.reasons])
```

## Pipeline

::: invoice_agent.pipeline

## Schema

::: invoice_agent.schema

## Policy

::: invoice_agent.policy.MatchPolicy

## Data loading

::: invoice_agent.data

## Matching

::: invoice_agent.match

## Validation

::: invoice_agent.validate

## Normalization

::: invoice_agent.normalize
