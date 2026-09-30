from __future__ import annotations

from pathlib import Path

from invoice_agent.evaluate import run_eval


def test_offline_extractor_eval(dataset: Path) -> None:
    report = run_eval(dataset)
    s = report.summary()
    assert s["invoices"] == 50
    assert s["extraction"]["fields"]["total"] >= 0.95
    assert s["matching"]["decision_accuracy"] == 1.0
    assert s["matching"]["exception_recall"] == 1.0
    assert s["matching"]["reason_recall"] == 1.0
    md = report.to_markdown()
    assert "| Decision accuracy | 100.0% |" in md
    assert "`q10`" in md  # the scanned invoice cannot be extracted without OCR


def test_oracle_eval_scores_matching_alone(dataset: Path) -> None:
    report = run_eval(dataset, oracle=True)
    assert report.extractor == "ground-truth"
    assert report.decision_accuracy() == 1.0
    assert report.po_link_accuracy() == 1.0
    assert "### Extraction" not in report.to_markdown()
