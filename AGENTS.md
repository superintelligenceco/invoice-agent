# AGENTS.md

Guidance for coding agents that work in this repository.

## Commands

- Install: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Lint: `ruff check .` and `ruff format --check .`. Fix with `ruff format . && ruff check --fix .`.
- Typecheck: `mypy` (strict, configured in `pyproject.toml`)
- Test: `pytest` (add `--cov` for coverage)
- Eval: `invoice-agent eval --min-decision-accuracy 1`
- Regenerate the dataset: `invoice-agent generate-dataset dataset`

Run lint, typecheck, test, and eval before you finish a change. All must pass.

## Conventions

- Python 3.11 or later, `from __future__ import annotations` in every module, full type hints.
- Money is `decimal.Decimal` everywhere. Never convert an amount to `float`.
- Models in `schema.py` keep `extra="forbid"`, so a typo fails loudly.
- Every finding is a `Reason` built with `reasons.reason()`, with a code from `reasons.CODES` and a
  message that names the line, the numbers, and the limit.
- Runtime dependencies are `pydantic`, `pdfplumber`, `pypdf`, `rapidfuzz`, and `httpx`. Ask before
  adding one.
- Tests never call a paid API. Mock the LLM endpoint with `httpx.MockTransport`.
- Commit messages follow Conventional Commits.

## Boundaries

- Don't hand-edit files in `dataset/`. Change the generator and regenerate.
- Don't commit `.venv/`, `dist/`, coverage output, ledgers, or eval reports.
- Don't weaken a test or an eval threshold to make it pass. Fix the code or explain why the
  expectation was wrong.
- Don't add real company names, real invoices, secrets, or machine-specific paths.
