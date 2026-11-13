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


# -- "what it does": the company's own words from its latest annual report -------------------------
OVERVIEW = re.compile(
    r"\b(business overview|corporate overview|company overview|about (?:us|the company|[A-Z][\w&]+)|"
    r"who we are|our business|at a glance|corporate snapshot)\b",
    re.I,
)
DESCRIBES = re.compile(r"\b(?:we are|we're|is an?|is one of|is india'?s|are one of|leading|largest)\b", re.I)
BUSINESS_NOUN = re.compile(
    r"manufactur|provider|lender|bank|services|solutions|company|platform|engineering|chemical|"
    r"financ|technolog|construction|retail|electronics|institution|conglomerate",
    re.I,
)
# self-descriptions that are about hiring, culture or awards, not the business
NOT_BUSINESS = re.compile(
    r"employer|employee|workplace|culture|great place|csr\b|award|certified|recogni[sz]ed", re.I
)
ABOUT_PROMPT = "about-v2"
ABOUT_SYSTEM = (
    "You pick, from numbered sentences taken from a company's annual report, the one that best says "
    "what the WHOLE company does: its businesses, products or services and customers. Reject sentences "
    "about a single product, segment or business line (e.g. 'one of the largest mortgage lenders'), "
    "slogans, awards, rankings without the business, and sentences that need context ('in this space'). "
    'Return JSON {"ids": [k]} with one id, or {"ids": []} if none describes the whole company.'
)


def _names(company: str) -> list[str]:
    """How a report refers to itself: 'CreditAccess', 'HDFC Bank', 'L&T', 'Infosys'."""
    words = [w for w in re.findall(r"[A-Za-z&.]+", company) if w.lower() not in {"limited", "ltd", "ltd."}]
    out = [words[0]] if words else []
    if len(words) >= 2:
        out.append(f"{words[0]} {words[1]}")
    if "&" in company:
        parts = [w for w in words if w != "&"]
        if len(parts) >= 2:
            out.append(f"{parts[0][0]}&{parts[1][0]}")
    return out


def _candidates(pages: list[str], company: str, limit: int = 30) -> list[tuple[int, str]]:
    """Sentences in the first 60 pages where the company describes itself ('X is a ...', 'We are
    one of ...'), cut to start at that self-description. Verbatim; page numbers kept."""
    names = "|".join(re.escape(n) for n in _names(company))
    rx = re.compile(
        rf"(?:\b(?:{names})\b[^.]{{0,40}}?|\bwe)\s+(?:is|are)\s+"
        rf"(?:a|an|one of|india'?s|the)\b[^.]{{20,260}}\.",
        re.I,
    )
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    for i, p in enumerate(pages[:60]):
        text = re.sub(r"\s+", " ", p or "")
        for m in rx.finditer(text):
            # start at the sentence's own beginning ("Kaynes Technology India Limited ('Kaynes' ...) is")
            lo = max(text.rfind(". ", 0, m.start()) + 2, m.start() - 160, 0)
            starts = [
                x.start() for x in re.finditer(rf"(?<![\w'‘’\"“])(?:{names})\b", text[lo : m.end()], re.I)
            ]
            start = lo + starts[-1] if starts else m.start()  # the last unquoted mention: after any heading
            sent = text[start : m.end()].strip()
            if NOT_BUSINESS.search(sent):
                continue
            if sent.lower() not in seen and BUSINESS_NOUN.search(sent):
                seen.add(sent.lower())
                out.append((i + 1, sent[0].upper() + sent[1:]))
    return out[:limit]


def about(conn: Connection, cid: int, router=None) -> dict:
    """Two lines in the company's own words, chosen from its latest annual report's overview pages,
    with the page cited. Nothing is paraphrased; when no page describes the business, say so."""
    row = conn.execute(
        "SELECT period, url, pages FROM documents WHERE company_id = %s AND kind = 'annual_report' "
        "AND pages IS NOT NULL ORDER BY filed_at DESC NULLS LAST LIMIT 1",
        (cid,),
    ).fetchone()
    if row is None:
        return {"text": None, "note": "No annual report read for this company yet."}
    period, url, pages = row
    name = conn.execute("SELECT name FROM companies WHERE id = %s", (cid,)).fetchone()
    cands = _candidates(pages, name[0] if name else "")
    if not cands:
        return {
            "text": None,
            "note": f"The {period} annual report's overview pages don't describe the business in a sentence.",
        }
    pick: list[int] = []
    if router is not None:
        from pydantic import BaseModel

        class Pick(BaseModel):
            ids: list[int]

        listing = "\n".join(f"[{k}] {s}" for k, (_, s) in enumerate(cands))
        try:
            res = router.call("EXTRACT", "about_pick", ABOUT_PROMPT, ABOUT_SYSTEM, listing, Pick)
            pick = [k for k in res.data.ids if 0 <= k < len(cands)][:1]  # type: ignore[attr-defined]
        except Exception:
            pick = []
    if not pick:
        return {
            "text": None,
            "note": f"No sentence in the {period} annual report's opening pages says plainly "
            "what the company does.",
        }
    chosen = [cands[k] for k in sorted(pick)]
    return {
        "text": " ".join(s for _, s in chosen),
        "page": chosen[0][0],
        "url": url,
        "period": period,
        "by": "picked by model, verbatim"
        if router is not None and pick != [0]
        else "first describing sentence, verbatim",
    }


def mix_line(biz: dict) -> str | None:
    """'What it does' as a fact from the results filings: the segment mix by revenue share."""
    segs = [x for x in biz.get("segments") or [] if x.get("share") is not None]
    if segs:
        segs = sorted(segs, key=lambda x: -x["share"])
        shown = segs[:4]
        rest = round(100 - sum(x["share"] for x in shown))
        parts = [f"{round(x['share'])}% {x['name']}" for x in shown] + (
            [f"{rest}% other"] if len(segs) > 4 and rest > 0 else []
        )
        return f"{biz.get('year') or ''} revenue by segment: {', '.join(parts)}".strip()
    if biz.get("single_segment"):
        ind = biz.get("industry")
        return f"{ind}: reports a single business segment" if ind else "Reports a single business segment"
    return None
