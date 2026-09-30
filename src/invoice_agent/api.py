"""Small HTTP service around the pipeline. Requires the ``api`` extra.

Run it with ``invoice-agent serve --pos pos.json --receipts receipts.json``.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from functools import cache
from importlib.resources import files
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from . import __version__
from .extract import Extractor
from .ingest import IngestError, load_pdf
from .match import Ledger
from .pipeline import Pipeline
from .policy import MatchPolicy
from .schema import GoodsReceipt, Invoice, PurchaseOrder, Result

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@cache
def _ui_page() -> str:
    """The single-page upload UI served at ``/``."""
    return files(__package__).joinpath("ui.html").read_text(encoding="utf-8")


def create_app(
    purchase_orders: Iterable[PurchaseOrder],
    receipts: Iterable[GoodsReceipt] = (),
    *,
    policy: MatchPolicy | None = None,
    extractor: Extractor | None = None,
    ledger: Ledger | None = None,
) -> FastAPI:
    """Build the app. The ledger lives in memory for the life of the process."""
    pipeline = Pipeline(
        list(purchase_orders), list(receipts), extractor=extractor, policy=policy, ledger=ledger
    )
    lock = threading.Lock()
    app = FastAPI(
        title="invoice-agent",
        version=__version__,
        summary="Invoice extraction and 2-way/3-way PO matching with explainable decisions.",
    )

    async def _read(file: UploadFile) -> bytes:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file is larger than 20 MB")
        return data

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def ui() -> str:
        return _ui_page()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "extractor": pipeline.extractor.name,
            "purchase_orders": len(pipeline.matcher.pos),
            "invoices_seen": len(pipeline.ledger.seen),
        }

    @app.post("/extract", response_model=Invoice)
    async def extract(file: UploadFile = File(...)) -> Invoice:  # noqa: B008
        data = await _read(file)
        try:
            doc = load_pdf(data, name=file.filename)
        except IngestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return pipeline.extractor.extract(doc)

    @app.post("/process", response_model=Result)
    async def process(file: UploadFile = File(...)) -> Result:  # noqa: B008
        data = await _read(file)
        try:
            doc = load_pdf(data, name=file.filename)
        except IngestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with lock:
            return pipeline.process_document(doc)

    @app.post("/match", response_model=Result)
    def match(invoice: Invoice) -> Result:
        """Validate and match an invoice that was extracted elsewhere."""
        with lock:
            return pipeline.process_invoice(invoice, source="api")

    return app
