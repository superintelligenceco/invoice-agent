"""Score extraction and matching against a labeled dataset.

A dataset directory contains ``manifest.json``, ``invoices/*.pdf``,
``ground_truth/*.json``, ``purchase_orders.json`` and ``receipts.json``, as
written by ``invoice-agent generate-dataset``. Invoices are processed in
manifest order, because duplicate and overbilling checks depend on history.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .data import load_purchase_orders, load_receipts
from .extract import Extractor
from .ingest import Document, load_pdf
from .normalize import normalize_doc_number, normalize_po, normalize_vendor
from .pipeline import Pipeline
from .policy import MatchPolicy
from .schema import Decision, Invoice, Result, Severity

HEADER_FIELDS: dict[str, Callable[[Invoice], Any]] = {
    "vendor": lambda i: normalize_vendor(i.vendor),
    "invoice_number": lambda i: normalize_doc_number(i.invoice_number),
    "invoice_date": lambda i: i.invoice_date,
    "due_date": lambda i: i.due_date,
    "po_number": lambda i: normalize_po(i.po_number),
    "currency": lambda i: i.currency,
    "subtotal": lambda i: i.subtotal,
    "discount": lambda i: i.discount,
    "tax": lambda i: i.tax,
    "total": lambda i: i.total,
}


@dataclass
class Case:
    file: str
    case: str
    description: str
    truth: Invoice
    expected_decision: Decision
    expected_po: str | None
    expected_codes: list[str]


@dataclass
class CaseResult:
    case: Case
    result: Result
    field_hits: dict[str, bool]
    lines_correct: int

    @property
    def codes(self) -> list[str]:
        return sorted({r.code for r in self.result.reasons if r.severity is not Severity.INFO})


@dataclass
class Report:
    extractor: str
    oracle: bool = False
    cases: list[CaseResult] = field(default_factory=list)

    # -- extraction ---------------------------------------------------------
    def field_accuracy(self) -> dict[str, float]:
        n = len(self.cases) or 1
        acc = {f: sum(c.field_hits[f] for c in self.cases) / n for f in HEADER_FIELDS}
        acc["line_items"] = sum(c.field_hits["line_items"] for c in self.cases) / n
        return acc

    def line_accuracy(self) -> float:
        total = sum(len(c.case.truth.line_items) for c in self.cases)
        return sum(c.lines_correct for c in self.cases) / total if total else 0.0

    def document_accuracy(self) -> float:
        n = len(self.cases) or 1
        return sum(all(c.field_hits.values()) for c in self.cases) / n

    # -- matching -----------------------------------------------------------
    def decision_accuracy(self) -> float:
        n = len(self.cases) or 1
        return sum(c.result.decision == c.case.expected_decision for c in self.cases) / n

    def po_link_accuracy(self) -> float:
        n = len(self.cases) or 1
        return (
            sum(
                normalize_po(c.result.po_number) == normalize_po(c.case.expected_po)
                for c in self.cases
            )
            / n
        )

    def exception_pr(self, positive: set[Decision]) -> tuple[float, float, int]:
        """Precision and recall for flagging invoices whose decision is in ``positive``."""
        tp = sum(
            c.result.decision in positive and c.case.expected_decision in positive
            for c in self.cases
        )
        pred = sum(c.result.decision in positive for c in self.cases)
        actual = sum(c.case.expected_decision in positive for c in self.cases)
        return _safe(tp, pred), _safe(tp, actual), actual

    def reason_pr(self) -> tuple[float, float, float]:
        tp = pred = actual = 0
        for c in self.cases:
            got, want = set(c.codes), set(c.case.expected_codes)
            tp += len(got & want)
            pred += len(got)
            actual += len(want)
        p, r = _safe(tp, pred), _safe(tp, actual)
        return p, r, _safe(2 * p * r, p + r)

    def confusion(self) -> dict[str, dict[str, int]]:
        labels = [d.value for d in Decision]
        table = {a: dict.fromkeys(labels, 0) for a in labels}
        for c in self.cases:
            table[c.case.expected_decision.value][c.result.decision.value] += 1
        return table

    def failures(self) -> list[CaseResult]:
        return [
            c
            for c in self.cases
            if c.result.decision != c.case.expected_decision
            or c.codes != sorted(c.case.expected_codes)
            or normalize_po(c.result.po_number) != normalize_po(c.case.expected_po)
            or (not self.oracle and not all(c.field_hits.values()))
        ]

    def summary(self) -> dict[str, Any]:
        exc_p, exc_r, exc_n = self.exception_pr({Decision.NEEDS_REVIEW, Decision.REJECT})
        rej_p, rej_r, rej_n = self.exception_pr({Decision.REJECT})
        rp, rr, rf = self.reason_pr()
        return {
            "extractor": self.extractor,
            "oracle": self.oracle,
            "invoices": len(self.cases),
            "extraction": {
                "fields": self.field_accuracy(),
                "line_item_accuracy": self.line_accuracy(),
                "document_exact_match": self.document_accuracy(),
            },
            "matching": {
                "decision_accuracy": self.decision_accuracy(),
                "po_link_accuracy": self.po_link_accuracy(),
                "exception_precision": exc_p,
                "exception_recall": exc_r,
                "exceptions": exc_n,
                "reject_precision": rej_p,
                "reject_recall": rej_r,
                "rejects": rej_n,
                "reason_precision": rp,
                "reason_recall": rr,
                "reason_f1": rf,
                "confusion": self.confusion(),
            },
        }

    def to_markdown(self, *, show_failures: bool = True) -> str:
        s = self.summary()
        ex, m = s["extraction"], s["matching"]
        n = s["invoices"]
        out: list[str] = []
        if not self.oracle:
            out += [
                f"### Extraction (`{self.extractor}` extractor, {n} invoices)",
                "",
                "| Field | Accuracy |",
                "| --- | ---: |",
            ]
            for name, value in ex["fields"].items():
                out.append(f"| `{name}` | {_pct(value)} |")
            out += [
                f"| line items, per line | {_pct(ex['line_item_accuracy'])} |",
                f"| whole document exact | {_pct(ex['document_exact_match'])} |",
                "",
            ]
        out += [
            f"### Matching and decisions (`{self.extractor}` extraction, {n} invoices)",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Decision accuracy | {_pct(m['decision_accuracy'])} |",
            f"| PO link accuracy | {_pct(m['po_link_accuracy'])} |",
            f"| Exception precision (review or reject, n={m['exceptions']}) "
            f"| {_pct(m['exception_precision'])} |",
            f"| Exception recall | {_pct(m['exception_recall'])} |",
            f"| Reject precision (n={m['rejects']}) | {_pct(m['reject_precision'])} |",
            f"| Reject recall | {_pct(m['reject_recall'])} |",
            f"| Reason code precision | {_pct(m['reason_precision'])} |",
            f"| Reason code recall | {_pct(m['reason_recall'])} |",
            "",
            "Confusion matrix (rows: expected, columns: predicted):",
            "",
            "| expected \\ predicted | " + " | ".join(m["confusion"]) + " |",
            "| --- |" + " ---: |" * len(m["confusion"]),
        ]
        for label, row in m["confusion"].items():
            out.append(f"| {label} | " + " | ".join(str(v) for v in row.values()) + " |")
        fails = self.failures()
        if show_failures and fails:
            out += ["", "Cases with any difference from ground truth:", ""]
            for c in fails:
                wrong = [f for f, ok in c.field_hits.items() if not ok]
                bits = []
                if c.result.decision != c.case.expected_decision:
                    bits.append(
                        f"decision {c.result.decision.value} "
                        f"(expected {c.case.expected_decision.value})"
                    )
                if c.codes != sorted(c.case.expected_codes):
                    bits.append(f"codes {c.codes} (expected {sorted(c.case.expected_codes)})")
                if normalize_po(c.result.po_number) != normalize_po(c.case.expected_po):
                    bits.append(f"PO {c.result.po_number} (expected {c.case.expected_po})")
                if wrong and not self.oracle:
                    bits.append(f"fields wrong: {', '.join(wrong)}")
                out.append(f"- `{c.case.case}` {c.case.description}: " + "; ".join(bits))
        return "\n".join(out) + "\n"


class _TruthExtractor:
    """Returns ground truth. Used to score matching on its own."""

    name = "ground-truth"

    def __init__(self, truths: dict[str, Invoice]) -> None:
        self.truths = truths

    def extract(self, doc: Document) -> Invoice:
        return self.truths[doc.source]


def load_cases(dataset: Path) -> list[Case]:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    cases = []
    for entry in manifest:
        stem = Path(entry["file"]).stem
        gt = json.loads((dataset / "ground_truth" / f"{stem}.json").read_text(encoding="utf-8"))
        cases.append(
            Case(
                file=gt["file"],
                case=gt["case"],
                description=gt["description"],
                truth=Invoice.model_validate(gt["invoice"]),
                expected_decision=Decision(gt["expected"]["decision"]),
                expected_po=gt["expected"]["po_number"],
                expected_codes=list(gt["expected"]["reason_codes"]),
            )
        )
    return cases


def run_eval(
    dataset: str | Path,
    extractor: Extractor | None = None,
    *,
    oracle: bool = False,
    policy: MatchPolicy | None = None,
) -> Report:
    """Run the whole dataset through a fresh pipeline and score it.

    With ``oracle=True`` the extractor is replaced by the ground truth, which
    scores the matching rules on their own.
    """
    root = Path(dataset)
    cases = load_cases(root)
    if oracle:
        extractor = _TruthExtractor({Path(c.file).name: c.truth for c in cases})
    pipeline = Pipeline(
        load_purchase_orders(root / "purchase_orders.json"),
        load_receipts(root / "receipts.json"),
        extractor=extractor,
        policy=policy,
    )
    report = Report(extractor=pipeline.extractor.name, oracle=oracle)
    for case in cases:
        doc = load_pdf(root / case.file)
        result = pipeline.process_document(doc)
        report.cases.append(_score(case, result))
    return report


def _score(case: Case, result: Result) -> CaseResult:
    got, want = result.invoice, case.truth
    hits = {name: fn(got) == fn(want) for name, fn in HEADER_FIELDS.items()}
    lines_correct = sum(
        1 for a, b in zip(got.line_items, want.line_items, strict=False) if _line_eq(a, b)
    )
    hits["line_items"] = len(got.line_items) == len(want.line_items) and lines_correct == len(
        want.line_items
    )
    return CaseResult(case=case, result=result, field_hits=hits, lines_correct=lines_correct)


def _line_eq(a: Any, b: Any) -> bool:
    return bool(
        a.quantity == b.quantity
        and a.unit_price == b.unit_price
        and a.amount == b.amount
        and normalize_doc_number(a.sku) == normalize_doc_number(b.sku)
        and " ".join(a.description.split()).lower() == " ".join(b.description.split()).lower()
    )


def _safe(num: float, den: float) -> float:
    return num / den if den else 0.0


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"
