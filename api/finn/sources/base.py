"""Source adapter interfaces. NSE is the only implementation today; another exchange or a
licensed feed can be added by implementing these without touching callers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    name: str
    isin: str | None
    series: str | None
    listed_on: date | None


@dataclass(frozen=True)
class Announcement:
    exch_id: str
    symbol: str
    ts: datetime  # timezone-aware, IST
    category: str | None
    subject: str | None
    pdf_url: str | None
    pdf_size_label: str | None
    industry: str | None
    raw: dict = field(hash=False, compare=False)


@dataclass(frozen=True)
class ResultsFiling:
    """A structured (XBRL) results filing."""

    source: str  # 'nse_cfr' | 'nse_integrated'
    symbol: str
    basis: str  # 'consolidated' | 'standalone'
    fmt: str | None  # 'N' | 'B' | 'F'
    period_start: date | None
    period_end: date
    audited: bool | None
    filed_at: datetime | None
    xbrl_url: str


@dataclass(frozen=True)
class AnnualReport:
    symbol: str
    fy_label: str  # 'FY2026' = year ending March 2026
    url: str
    filed_at: datetime | None
    size_label: str | None


class FilingsSource(Protocol):
    name: str

    def announcements(self, symbol: str, start: date, end: date) -> list[Announcement]: ...

    def recent_feed(self) -> list[Announcement]: ...


class FundamentalsSource(Protocol):
    name: str

    def results_filings(self, symbol: str) -> list[ResultsFiling]: ...

    def annual_reports(self, symbol: str) -> list[AnnualReport]: ...


class DocumentFetcher(Protocol):
    def fetch(self, url: str) -> bytes: ...


class SymbolMaster(Protocol):
    def symbols(self) -> list[SymbolInfo]: ...
