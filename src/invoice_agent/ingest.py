"""PDF ingestion: turn a file into per-page text.

The text layer is read with pdfplumber, with pypdf as a fallback. Pages
without a text layer can go through OCR when the ``ocr`` extra and the
Tesseract binary are installed.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class Document:
    """Text pulled out of one PDF."""

    source: str
    pages: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.pages)

    @property
    def has_text(self) -> bool:
        return any(p.strip() for p in self.pages)


class IngestError(RuntimeError):
    pass


def load_pdf(source: str | Path | bytes, *, ocr: bool = False, name: str | None = None) -> Document:
    """Read a PDF from a path or raw bytes.

    Args:
        source: File path or PDF bytes.
        ocr: Run OCR on pages that have no text layer.
        name: Display name when ``source`` is bytes.
    """
    if isinstance(source, bytes):
        data = source
        label = name or "<bytes>"
    else:
        path = Path(source)
        data = path.read_bytes()
        label = name or path.name
    if not data.startswith(b"%PDF"):
        raise IngestError(f"{label}: not a PDF file")

    pages = _pdfplumber_pages(data)
    if pages is None or not any(p.strip() for p in pages):
        fallback = _pypdf_pages(data)
        if fallback is not None and any(p.strip() for p in fallback):
            pages = fallback
    if pages is None:
        raise IngestError(f"{label}: could not parse PDF")

    doc = Document(source=label, pages=pages)
    if ocr:
        for i, text in enumerate(pages):
            if not text.strip():
                doc.pages[i] = _ocr_page(data, i)
                doc.ocr_pages.append(i)
    return doc


def _pdfplumber_pages(data: bytes) -> list[str] | None:
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [page.extract_text(x_tolerance=1.5, y_tolerance=3) or "" for page in pdf.pages]
    except Exception as exc:  # pdfminer raises many exception types on bad input
        log.debug("pdfplumber failed: %s", exc)
        return None


def _pypdf_pages(data: bytes) -> list[str] | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        log.debug("pypdf failed: %s", exc)
        return None


def _ocr_page(data: bytes, index: int) -> str:
    try:
        import pdfplumber
        import pytesseract
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise IngestError(
            "OCR requested but the 'ocr' extra is not installed: pip install 'invoice-agent[ocr]'"
        ) from exc
    with pdfplumber.open(io.BytesIO(data)) as pdf:  # pragma: no cover - needs tesseract
        image = pdf.pages[index].to_image(resolution=300).original
        return str(pytesseract.image_to_string(image))
