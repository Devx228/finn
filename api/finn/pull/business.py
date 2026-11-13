"""Business snapshot from the company's own results filing (no annual report, no model).

The annual (full-year) XBRL results carry the segment note: one context per reportable segment,
each with SegmentRevenue and SegmentProfitLossBeforeTaxAndFinanceCosts, and a text fact
DescriptionOfReportableSegment that names it. Numbers come from `fin_facts`; names from the
cached XBRL file (read from the local cache only — never fetched here). Code computes the mix,
margins and growth; reconciliation rows ("Less: inter-segment…", "Add: exceptional…",
"Unallocable…") are not segments and are skipped. A company that files as single-segment says so.
"""

from __future__ import annotations

import re
from datetime import date

from psycopg import Connection

from finn.fin.xbrl import parse_xbrl
from finn.sources.http import PoliteClient

NOT_A_SEGMENT = re.compile(
    r"^\s*(?:less|add)\b|inter[- ]?segment|unallocable|unallocated|elimination|reconcil|total", re.I
)
REV = "SegmentRevenue"
PROFIT = "SegmentProfitLossBeforeTaxAndFinanceCosts"


def _annual_periods(conn: Connection, cid: int) -> list[tuple[date, date, int, str, str]]:
    """Full-year periods with segment revenue, newest first: (start, end, fin_filing_id, basis, url)."""
    rows = conn.execute(
        "SELECT DISTINCT x.period_start, x.period_end, ff.id, ff.basis, ff.xbrl_url, ff.filed_at "
        "FROM fin_facts x JOIN fin_filings ff ON ff.id = x.fin_filing_id "
        "WHERE ff.company_id = %s AND x.concept = %s AND x.dims <> '' "
        "AND x.period_start IS NOT NULL AND x.period_end - x.period_start >= 360 "
        "ORDER BY x.period_end DESC, ff.filed_at DESC",
        (cid, REV),
    ).fetchall()
    best: dict[date, tuple] = {}
    for s, e, fid, basis, url, _f in rows:
        if e not in best or (basis == "consolidated" and best[e][3] != "consolidated"):
            best[e] = (s, e, fid, basis, url)
    return [best[e] for e in sorted(best, reverse=True)]


def _declared(conn: Connection, cid: int) -> str | None:
    """'Single segment' / 'Multi segment' as the latest cached results filing declares it."""
    for (url,) in conn.execute(
        "SELECT xbrl_url FROM fin_filings WHERE company_id = %s "
        "ORDER BY period_end DESC, filed_at DESC LIMIT 4",
        (cid,),
    ).fetchall():
        hit = PoliteClient("NSE").cached(url, None)
        if hit:
            v = parse_xbrl(hit.content).meta.get("IsCompanyReportingMultisegmentOrSingleSegment")
            if v:
                return v
    return None


def _labels(url: str) -> dict[str, str]:
    hit = PoliteClient("NSE").cached(url, None)
    return parse_xbrl(hit.content).labels if hit else {}


def _segments(conn: Connection, period: tuple) -> tuple[list[dict], str | None]:
    s, e, fid, _basis, url = period
    rows = conn.execute(
        "SELECT x.concept, x.dims, x.value FROM fin_facts x WHERE x.fin_filing_id = %s "
        "AND x.concept = ANY(%s) AND x.dims <> '' AND x.period_start = %s AND x.period_end = %s",
        (fid, [REV, PROFIT], s, e),
    ).fetchall()
    labels = _labels(url)
    # revenue and profit sit on different axes but share the member ("…Segments2Member")
    member_label = {d.split("=", 1)[-1]: n for d, n in labels.items() if "Segment" in d}
    by: dict[str, dict] = {}
    for concept, dims, value in rows:
        by.setdefault(dims.split("=", 1)[-1], {})[concept] = float(value) / 1e7
    out = []
    for member, v in by.items():
        name = member_label.get(member)
        rev = v.get(REV)
        if not name or rev is None or rev <= 0 or NOT_A_SEGMENT.search(name):
            continue
        out.append({"name": name.replace("&amp;", "&"), "revenue": round(rev, 1), "ebit": v.get(PROFIT)})
    return out, (None if labels else "segment names not in the cached filing")


def snapshot(conn: Connection, cid: int, industry: str | None, fy_start: int = 4) -> dict:
    periods = _annual_periods(conn, cid)
    base: dict = {"industry": industry, "segments": [], "single_segment": False, "year": None, "source": None}
    if not periods:
        declared = _declared(conn, cid)
        if declared and declared.lower().startswith("single"):
            return {
                **base,
                "single_segment": True,
                "note": "Files as a single segment (its results filing says so).",
            }
        return {**base, "note": "No full-year segment note in the results filings read."}
    cur = periods[0]
    segs, problem = _segments(conn, cur)
    if problem:
        return {**base, "note": problem}
    # growth only like-for-like: same basis, a segment of exactly the same name a year earlier
    prior = [p for p in periods[1:] if p[3] == cur[3] and (cur[1] - p[1]).days in range(360, 371)]
    prev = {x["name"]: x for x in (_segments(conn, prior[0])[0] if prior else [])}
    total = sum(x["revenue"] for x in segs)
    segs = [x for x in segs if total and x["revenue"] / total >= 0.001]
    for x in segs:
        x["share"] = round(x["revenue"] / total * 100, 1) if total else None
        x["margin"] = round(x["ebit"] / x["revenue"] * 100, 1) if x.get("ebit") is not None else None
        x["ebit"] = round(x["ebit"], 1) if x.get("ebit") is not None else None
        p = prev.get(x["name"])
        x["yoy"] = round((x["revenue"] / p["revenue"] - 1) * 100, 1) if p and p["revenue"] else None
    segs.sort(key=lambda x: -x["revenue"])
    end = cur[1]
    return {
        **base,
        "year": f"CY{end.year}"
        if fy_start == 1
        else f"FY{(end.year + (1 if end.month >= fy_start else 0)) % 100:02d}",
        "period_end": str(end),
        "basis": cur[3],
        "segments": segs,
        "single_segment": len(segs) <= 1,
        "segment_total": round(total, 1),
        "source": {"xbrl": cur[4]},
        "note": None,
    }
