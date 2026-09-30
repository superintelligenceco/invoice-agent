"""Command-line interface: ``invoice-agent <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .data import load_purchase_orders, load_receipts
from .extract import get_extractor
from .ingest import IngestError, load_pdf
from .match import Ledger
from .pipeline import Pipeline
from .policy import MatchPolicy
from .schema import Decision, Result, Severity

DEFAULT_DATASET = Path("dataset")

_MARK = {Severity.REJECT: "x", Severity.REVIEW: "!", Severity.INFO: "i"}
_LABEL = {
    Decision.AUTO_APPROVE: "AUTO-APPROVE",
    Decision.NEEDS_REVIEW: "NEEDS REVIEW",
    Decision.REJECT: "REJECT",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (IngestError, FileNotFoundError, ValueError) as exc:
        print(f"invoice-agent: error: {exc}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="invoice-agent",
        description="Extract invoice PDFs and match them to purchase orders and receipts.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="Extract one PDF to JSON")
    ex.add_argument("pdf", type=Path)
    _extractor_args(ex)
    ex.set_defaults(func=cmd_extract)

    pr = sub.add_parser("process", help="Extract, validate and match one or more PDFs, in order")
    pr.add_argument("pdfs", type=Path, nargs="+")
    pr.add_argument("--pos", type=Path, required=True, help="Purchase orders (.json, .csv, .db)")
    pr.add_argument("--receipts", type=Path, help="Goods receipts (.json, .csv, .db)")
    pr.add_argument("--policy", type=Path, help="JSON file with MatchPolicy overrides")
    pr.add_argument(
        "--ledger",
        type=Path,
        help="JSON file that remembers processed invoices across runs (created if missing)",
    )
    pr.add_argument("--json", action="store_true", help="Print JSON lines instead of text")
    _extractor_args(pr)
    pr.set_defaults(func=cmd_process)

    ev = sub.add_parser("eval", help="Score extraction and matching on a labeled dataset")
    ev.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ev.add_argument(
        "--oracle",
        action="store_true",
        help="Use ground-truth extraction to score the matching rules on their own",
    )
    ev.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ev.add_argument("--output", type=Path, help="Also write the report to this file")
    ev.add_argument(
        "--min-decision-accuracy",
        type=float,
        default=0.0,
        help="Exit with status 1 if decision accuracy is below this fraction",
    )
    _extractor_args(ev)
    ev.set_defaults(func=cmd_eval)

    gen = sub.add_parser("generate-dataset", help="Write the synthetic dataset (needs [synth])")
    gen.add_argument("out", type=Path, nargs="?", default=DEFAULT_DATASET)
    gen.set_defaults(func=cmd_generate)

    sv = sub.add_parser("serve", help="Run the HTTP API (needs [api])")
    sv.add_argument("--pos", type=Path, required=True)
    sv.add_argument("--receipts", type=Path)
    sv.add_argument("--policy", type=Path)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    _extractor_args(sv)
    sv.set_defaults(func=cmd_serve)
    return p


def _extractor_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--extractor",
        choices=("layout", "llm"),
        default="layout",
        help="layout: offline rules (default). llm: OpenAI-compatible API",
    )
    p.add_argument("--ocr", action="store_true", help="OCR pages without a text layer ([ocr])")


def cmd_extract(args: argparse.Namespace) -> int:
    doc = load_pdf(args.pdf, ocr=args.ocr)
    invoice = get_extractor(args.extractor).extract(doc)
    print(invoice.model_dump_json(indent=2))
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    ledger = Ledger.load(args.ledger) if args.ledger else None
    pipeline = Pipeline(
        load_purchase_orders(args.pos),
        load_receipts(args.receipts) if args.receipts else (),
        extractor=get_extractor(args.extractor),
        policy=MatchPolicy.from_file(args.policy) if args.policy else None,
        ledger=ledger,
        ocr=args.ocr,
    )
    for pdf in args.pdfs:
        result = pipeline.process_pdf(pdf)
        if args.json:
            print(result.model_dump_json())
        else:
            print(format_result(result))
    if args.ledger:
        pipeline.ledger.save(args.ledger)
    return 0


def format_result(result: Result) -> str:
    """Human-readable, multi-line summary of one processed invoice."""
    inv = result.invoice
    lines = [f"{result.source}: {_LABEL[result.decision]}"]
    facts = [
        ("vendor", inv.vendor),
        ("invoice", inv.invoice_number),
        ("date", inv.invoice_date.isoformat() if inv.invoice_date else None),
        ("total", f"{inv.currency or ''} {inv.total}".strip() if inv.total is not None else None),
        ("po", _po_label(result)),
    ]
    for key, value in facts:
        lines.append(f"  {key:<8}{value if value is not None else '-'}")
    if result.line_matches:
        matched = sum(m.po_line is not None for m in result.line_matches)
        lines.append(f"  lines   {matched}/{len(result.line_matches)} matched to PO lines")
    for r in result.reasons:
        lines.append(f"  [{_MARK[r.severity]}] {r.code}: {r.message}")
    return "\n".join(lines)


def _po_label(result: Result) -> str | None:
    if not result.po_number:
        return None
    return f"{result.po_number} ({result.match_type})" if result.match_type else result.po_number


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import run_eval

    if not (args.dataset / "manifest.json").exists():
        raise FileNotFoundError(f"{args.dataset}/manifest.json not found")
    extractor = None if args.oracle else get_extractor(args.extractor)
    report = run_eval(args.dataset, extractor, oracle=args.oracle)
    text = (
        json.dumps(report.summary(), indent=2) + "\n"
        if args.format == "json"
        else report.to_markdown()
    )
    sys.stdout.write(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    return 1 if report.decision_accuracy() < args.min_decision_accuracy else 0


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        from .synth.generate import write_dataset
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise ValueError("install the synth extra: pip install 'invoice-agent[synth]'") from exc
    counts = write_dataset(args.out)
    print(
        f"wrote {counts['invoices']} invoices, {counts['purchase_orders']} purchase orders "
        f"and {counts['receipts']} receipts to {args.out}"
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover - blocks on a server
    try:
        import uvicorn

        from .api import create_app
    except ImportError as exc:
        raise ValueError("install the api extra: pip install 'invoice-agent[api]'") from exc
    app = create_app(
        load_purchase_orders(args.pos),
        load_receipts(args.receipts) if args.receipts else (),
        policy=MatchPolicy.from_file(args.policy) if args.policy else None,
        extractor=get_extractor(args.extractor),
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
