from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_agent.cli import main

from .conftest import DATASET

POS = str(DATASET / "purchase_orders.json")
RECEIPTS = str(DATASET / "receipts.json")


def test_extract(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["extract", str(DATASET / "invoices" / "001_q01.pdf")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["invoice_number"] == "QOS-10401"
    assert data["total"] == "239.56"


def test_process_text_output(capsys: pytest.CaptureFixture[str]) -> None:
    pdf = str(DATASET / "invoices" / "017_b05.pdf")
    assert main(["process", pdf, "--pos", POS, "--receipts", RECEIPTS]) == 0
    out = capsys.readouterr().out
    assert "017_b05.pdf: REJECT" in out
    assert "[x] QTY_EXCEEDS_ORDERED" in out


def test_process_json_and_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "ledger.json"
    pdf = str(DATASET / "invoices" / "001_q01.pdf")
    args = ["process", pdf, "--pos", POS, "--receipts", RECEIPTS, "--json", "--ledger", str(ledger)]
    assert main(args) == 0
    assert main(args) == 0
    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert first["decision"] == "auto_approve"
    assert second["decision"] == "reject"
    assert ledger.exists()


def test_process_with_policy_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"price_tolerance_pct": "0.10"}))
    pdf = str(DATASET / "invoices" / "016_b04.pdf")
    assert (
        main(["process", pdf, "--pos", POS, "--receipts", RECEIPTS, "--policy", str(policy)]) == 0
    )
    assert "AUTO-APPROVE" in capsys.readouterr().out


def test_eval_markdown_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "report.md"
    rc = main(
        ["eval", "--dataset", str(DATASET), "--output", str(out), "--min-decision-accuracy", "1"]
    )
    assert rc == 0
    assert "Decision accuracy" in out.read_text()
    capsys.readouterr()
    assert main(["eval", "--dataset", str(DATASET), "--format", "json", "--oracle"]) == 0
    assert json.loads(capsys.readouterr().out)["matching"]["decision_accuracy"] == 1.0


def test_eval_missing_dataset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eval", "--dataset", str(tmp_path)]) == 2
    assert "manifest.json not found" in capsys.readouterr().err


def test_shipped_dataset_matches_the_generator(tmp_path: Path) -> None:
    """Ground truth, POs and receipts in the repo must equal a fresh generator run.

    PDF bytes are not compared, because they depend on the reportlab version.
    """
    pytest.importorskip("reportlab")
    assert main(["generate-dataset", str(tmp_path)]) == 0
    fresh = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    shipped = sorted(p.relative_to(DATASET) for p in DATASET.rglob("*") if p.is_file())
    assert fresh == shipped
    for rel in fresh:
        if rel.suffix == ".json":
            assert (tmp_path / rel).read_text() == (DATASET / rel).read_text(), rel
