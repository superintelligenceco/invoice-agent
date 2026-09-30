"""Pluggable invoice extractors."""

from __future__ import annotations

from .base import Extractor
from .layout import LayoutExtractor
from .llm import LLMExtractor

__all__ = ["Extractor", "LLMExtractor", "LayoutExtractor", "get_extractor"]


def get_extractor(name: str) -> Extractor:
    """Return an extractor by name: ``layout`` (offline) or ``llm``."""
    if name == "layout":
        return LayoutExtractor()
    if name == "llm":
        return LLMExtractor()
    raise ValueError(f"unknown extractor {name!r}; choose 'layout' or 'llm'")
