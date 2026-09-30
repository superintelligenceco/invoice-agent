"""Extractor interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..ingest import Document
from ..schema import Invoice


@runtime_checkable
class Extractor(Protocol):
    """Turns ingested document text into an :class:`Invoice`.

    Implementations must not raise on unreadable input. Return an
    ``Invoice`` with the fields that could not be read left as ``None``.
    """

    name: str

    def extract(self, doc: Document) -> Invoice: ...
