"""Response models. Every GET returns a render-ready view-model; web/lib/types.ts mirrors these."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

Window = Literal["24h", "3d", "7d", "30d"]
Tier = Literal["now", "worth", "buried"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    db: Literal["ok", "down"]


class BriefCounts(BaseModel):
    filings: int
    now: int
    worth: int
    buried: int


class BriefRow(BaseModel):
    id: str
    tier: Tier
    symbol: str
    company: str
    ts: datetime
    category: str
    category_label: str
    sub_type: str | None = None
    kind: str
    headline: str
    score: int
    components: dict[str, Any]  # score breakdown for "Why is this here?"
    pdf_url: str | None = None  # the original filing on NSE (never re-hosted)
    filing_ids: list[int]
    bundled: int = 0
    card: dict[str, Any] | None = None  # results card etc.
    network: dict[str, Any] | None = None  # who is this person / who can help (spec §9)


class BuriedGroup(BaseModel):
    label: str
    count: int
    items: list[BriefRow]


class Brief(BaseModel):
    window: Window
    as_of: datetime
    placeholder: bool = False
    counts: BriefCounts
    now: list[BriefRow] = []
    worth: list[BriefRow] = []
    buried: list[BuriedGroup] = []
    source_credit: str | None = None
