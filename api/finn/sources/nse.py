"""NSE adapter: symbol master, announcements, structured results, annual reports, documents.

Endpoints verified 2026-11-12 (DECISIONS.md). All traffic goes through one PoliteClient.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from finn.sources.base import Announcement, AnnualReport, ResultsFiling, SymbolInfo
from finn.sources.http import PoliteClient

IST = ZoneInfo("Asia/Kolkata")
API = "https://www.nseindia.com/api/"
MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
RSS_URL = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"

HOUR = 3600.0
LISTING_TTL = 6 * HOUR  # announcement / results listings change; documents never do
MASTER_TTL = 7 * 24 * HOUR


def _dt(s: str | None, fmts: tuple[str, ...]) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for f in fmts:
        try:
            return datetime.strptime(s, f).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _d(s: str | None) -> date | None:
    d = _dt(s, ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"))
    return d.date() if d else None


class NSE:
    name = "NSE"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.http = client or PoliteClient("NSE", min_interval=1.2)

    # -- symbol master -------------------------------------------------------
    def symbols(self) -> list[SymbolInfo]:
        text = self.http.get(MASTER_URL, ttl_s=MASTER_TTL).content.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(text))
        out = []
        for r in rows:
            r = {k.strip(): (v or "").strip() for k, v in r.items()}
            out.append(
                SymbolInfo(
                    symbol=r["SYMBOL"],
                    name=r["NAME OF COMPANY"],
                    isin=r.get("ISIN NUMBER") or None,
                    series=r.get("SERIES") or None,
                    listed_on=_d(r.get("DATE OF LISTING")),
                )
            )
        return out

    # -- announcements -------------------------------------------------------
    @staticmethod
    def _announcement(x: dict) -> Announcement | None:
        ts = _dt(x.get("an_dt") or x.get("sort_date"), ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"))
        if ts is None or not x.get("symbol"):
            return None
        exch_id = (
            str(x.get("seq_id") or "") or f"{x['symbol']}|{x.get('an_dt')}|{x.get('attchmntFile')}"
        )
        return Announcement(
            exch_id=exch_id,
            symbol=x["symbol"],
            ts=ts,
            category=x.get("desc"),
            subject=(x.get("attchmntText") or "").strip() or None,
            pdf_url=x.get("attchmntFile") or None,
            pdf_size_label=x.get("attFileSize"),
            industry=x.get("smIndustry"),
            raw=x,
        )

    def announcements(self, symbol: str, start: date, end: date) -> list[Announcement]:
        rows = self.http.get(
            API + "corporate-announcements",
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": start.strftime("%d-%m-%Y"),
                "to_date": end.strftime("%d-%m-%Y"),
            },
            ttl_s=LISTING_TTL,
        ).json()
        assert isinstance(rows, list), f"unexpected announcements payload for {symbol}"
        return [a for a in (self._announcement(x) for x in rows) if a]

    def recent_feed(self) -> list[Announcement]:
        """Rolling ~1-day RSS of all companies' announcements (for the incremental job)."""
        xml = self.http.get(RSS_URL, ttl_s=15 * 60).content.decode("utf-8", "replace")
        out = []
        for item in re.findall(r"<item>(.*?)</item>", xml, re.S):

            def tag(t: str, item: str = item) -> str | None:
                m = re.search(rf"<{t}>(.*?)</{t}>", item, re.S)
                return m.group(1).strip() if m else None

            link = tag("link")
            sym = re.search(r"/corporate/([A-Z0-9&\-]+)_\d", link or "")
            desc = tag("description") or ""
            subj = desc.split("|SUBJECT:")
            ts = _dt(tag("pubDate"), ("%d-%b-%Y %H:%M:%S",))
            if not ts or not sym:
                continue
            out.append(
                Announcement(
                    exch_id=f"rss|{link}",
                    symbol=sym.group(1),
                    ts=ts,
                    category=subj[1].strip() if len(subj) > 1 else None,
                    subject=subj[0].strip() or None,
                    pdf_url=link,
                    pdf_size_label=None,
                    industry=None,
                    raw={"title": tag("title"), "link": link, "description": desc},
                )
            )
        return out

    # -- structured results --------------------------------------------------
    def results_filings(self, symbol: str) -> list[ResultsFiling]:
        out: list[ResultsFiling] = []
        old = self.http.get(
            API + "corporates-financial-results",
            params={"index": "equities", "symbol": symbol, "period": "Quarterly"},
            ttl_s=LISTING_TTL,
        ).json()
        for x in old if isinstance(old, list) else []:
            end = _d(x.get("toDate"))
            if not end or not x.get("xbrl") or not str(x["xbrl"]).endswith(".xml"):
                continue
            out.append(
                ResultsFiling(
                    source="nse_cfr",
                    symbol=symbol,
                    basis="consolidated"
                    if x.get("consolidated") == "Consolidated"
                    else "standalone",
                    fmt=x.get("bank") or None,
                    period_start=_d(x.get("fromDate")),
                    period_end=end,
                    audited=(x.get("audited") == "Audited") if x.get("audited") else None,
                    filed_at=_dt(x.get("filingDate"), ("%d-%b-%Y %H:%M",)),
                    xbrl_url=x["xbrl"],
                )
            )
        new = self.http.get(
            API + "integrated-filing-results",
            params={"index": "equities", "symbol": symbol, "type": "Integrated Filing- Financials"},
            ttl_s=LISTING_TTL,
        ).json()
        rows = new.get("data", []) if isinstance(new, dict) else (new or [])
        for x in rows:
            end = _d((x.get("qe_Date") or "").title())
            if not end or not x.get("xbrl"):
                continue
            out.append(
                ResultsFiling(
                    source="nse_integrated",
                    symbol=symbol,
                    basis="consolidated"
                    if x.get("consolidated") == "Consolidated"
                    else "standalone",
                    fmt=None,  # read from the XBRL itself
                    period_start=None,
                    period_end=end,
                    audited=(x.get("audited") == "Audited") if x.get("audited") else None,
                    filed_at=_dt(x.get("broadcast_Date"), ("%d-%b-%Y %H:%M:%S",)),
                    xbrl_url=x["xbrl"],
                )
            )
        return out

    # -- annual reports ------------------------------------------------------
    def annual_reports(self, symbol: str) -> list[AnnualReport]:
        j = self.http.get(
            API + "annual-reports", params={"index": "equities", "symbol": symbol}, ttl_s=24 * HOUR
        ).json()
        rows = j.get("data", []) if isinstance(j, dict) else []
        out = []
        for x in rows:
            if not x.get("fileName") or not x.get("toYr"):
                continue
            out.append(
                AnnualReport(
                    symbol=symbol,
                    fy_label=f"FY{x['toYr']}",
                    url=x["fileName"],
                    filed_at=_dt(x.get("broadcast_dttm"), ("%d-%b-%Y %H:%M:%S",)),
                    size_label=x.get("attFileSize"),
                )
            )
        return out

    # -- documents -----------------------------------------------------------
    def fetch(self, url: str) -> bytes:
        """Download a document once; cached forever."""
        return self.http.get(url, ttl_s=None).content


TRANSCRIPT_RE = re.compile(r"\btranscript", re.I)


def is_transcript(a: Announcement) -> bool:
    return bool(a.pdf_url and a.subject and TRANSCRIPT_RE.search(a.subject))
