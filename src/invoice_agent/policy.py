"""Tunable matching policy."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MatchPolicy(BaseModel):
    """Thresholds used by validation and matching. All fields have safe defaults."""

    model_config = ConfigDict(extra="forbid")

    price_tolerance_pct: Decimal = Field(
        default=Decimal("0.02"),
        description="Allowed unit-price increase over the PO, as a fraction",
    )
    price_tolerance_abs: Decimal = Field(
        default=Decimal("0.05"), description="Allowed unit-price increase in currency units"
    )
    qty_tolerance_pct: Decimal = Field(
        default=Decimal("0"), description="Allowed quantity over ordered or received, as a fraction"
    )
    line_rounding: Decimal = Field(
        default=Decimal("0.02"), description="Per-line rounding difference reported as info only"
    )
    total_tolerance: Decimal = Field(
        default=Decimal("0.02"), description="Allowed difference on subtotal and total checks"
    )
    vendor_match_threshold: float = Field(
        default=85.0,
        description="Minimum fuzzy score (0-100) for the invoice vendor to equal the PO vendor",
    )
    line_match_threshold: float = Field(
        default=0.55, description="Minimum description similarity (0-1) to pair lines without a SKU"
    )
    duplicate_window_days: int = Field(
        default=14,
        description="Same vendor and total within this many days is a possible duplicate",
    )
    require_po_number: bool = Field(
        default=True, description="Send invoices without a printed PO number to review"
    )

    @classmethod
    def from_file(cls, path: str | Path) -> MatchPolicy:
        return cls.model_validate(json.loads(Path(path).read_text()))
