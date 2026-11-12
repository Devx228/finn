"""Response models. Every GET returns a render-ready view-model; the TypeScript types in
web/lib/types.ts mirror these (generated from OpenAPI once the shapes settle)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Window = Literal["24h", "3d", "7d", "30d"]
Tier = Literal["now", "worth", "buried"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    db: Literal["ok", "down"]


class BriefItem(BaseModel):
    id: str
    tier: Tier
    company: str
    headline: str


class BriefCounts(BaseModel):
    filings: int
    now: int
    worth: int
    buried: int


class Brief(BaseModel):
    window: Window
    as_of: datetime
    # True while the brief is wiring-test content rather than real filings (Phase 0 only).
    placeholder: bool = False
    counts: BriefCounts
    items: list[BriefItem]
