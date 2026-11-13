"""What the company itself later reported for a guided metric (owner's rule, SPEC §10.3):
when the company reports the guided metric, that number is the actual. We compute our own figure
only as a cross-check, and use it alone only where the filing leaves no room for definition
(revenue, revenue growth in rupees, EBITDA margin as defined on the results card).

Read from management's own sentences in later earnings calls. A sentence counts as a reported
outcome when it states a result (past/static verb), names one of the tracked metrics next to its
number, and says which period it covers:
  - an explicit year ("for FY26", "in FY '26") no later than the call's own year;
  - "the year" / "full year" / "trailing 12 months" in a Q4 call → that fiscal year;
  - "H1" / "first half" in a Q2 call, "nine months" / "9M" in a Q3 call → year to date;
  - a balance-sheet growth (loan book / AUM) stated YoY in a Q4 call → the year (a stock's YoY at
    year end is the year's growth).
Forward-looking clauses are cut first ("…compared to our guidance of 15%" keeps only the result).
Analysts' and the moderator's lines never count.
"""

from __future__ import annotations

import re
from datetime import date

from finn.pull import guidance as gd

OUTCOME = re.compile(
    r"\b(?:was|were|is|stood at|stands at|came in at|came at|ended(?: the year)? (?:at|with)|closed at|"
    r"grew|has grown|have grown|we've grown|we have grown|grown at|delivered|reported|recorded|had|"
    r"registered|translating (?:in)?to|translates (?:in)?to|achieved|at)\b",
    re.I,
)
FUTURE = re.compile(
    r"\bwill\b|\bwould\b|\bexpect|\btarget|\baim|\boutlook\b|\bguid(?:e|ing)\b|\bplan\b|\bshould\b|"
    r"\bgoing forward\b|\bnext year\b",
    re.I,
)
VS_GUIDANCE = re.compile(r"\b(?:compared (?:to|with)|against|versus|vs\.?|as against)\b.*$", re.I)
YEAR_WORDS = re.compile(
    r"\bthe year\b|\bfull[- ]year\b|\bfor the year\b|trailing (?:12|twelve)[- ]months?", re.I
)
H1 = re.compile(r"\bH1\b|first half", re.I)
NINE = re.compile(r"nine months|\b9M\b", re.I)
YOY = re.compile(r"y-?o-?y|y-on-y|year[- ]on[- ]year", re.I)
QUARTER_ONLY = re.compile(
    r"\bfor the quarter\b|\bthis quarter\b|\bin (?:the )?q[1-4]\b|\bq[1-4]\s*(?:fy|')|"
    r"(?:first|second|third|fourth) quarter|quarter-on-quarter|q-?o-?q|sequential",
    re.I,
)
PERIOD_TOKEN = re.compile(r"\b(?:FY|Q[1-4]|H[12])\s*'?\s*\d{2,4}\b|\bQ[1-4]\b|\b20\d\d\b|12[- ]months?", re.I)
# A year right after a quarter/half marker is that quarter's, not the year's ("Q4 FY26").
PERIOD_BEFORE = re.compile(r"(?:\bq[1-4]|\bh[12]|quarter|months|9m)\W{0,3}(?:of\s+)?$", re.I)
STOCK_METRICS = {"aum_growth"}
CC = re.compile(r"constant currency|\bcc\b", re.I)


def _fy_of(d: date, fy_start: int) -> int:
    return d.year + (1 if fy_start != 1 and d.month >= fy_start else 0)


def _nearest_period(s: str, a: int, b: int, limit: int, qn: int, call_fy: int):
    """The period marker closest to the metric-and-number span [a, b) decides what the number
    covers: "quarter" (skip), (fy, quarters), or None. Markers after the number count only up to
    the next number."""
    marks: list[tuple[int, object]] = []
    for m in QUARTER_ONLY.finditer(s):
        marks.append((m.start(), "quarter"))
    for m in YEAR_WORDS.finditer(s):
        marks.append((m.start(), (call_fy, 4) if qn == 4 else "quarter"))
    for m in H1.finditer(s):
        marks.append((m.start(), (call_fy, 2) if qn == 2 else "quarter"))
    for m in NINE.finditer(s):
        marks.append((m.start(), (call_fy, 3) if qn == 3 else "quarter"))
    for m in gd.FY.finditer(s):
        if not PERIOD_BEFORE.search(s[max(0, m.start() - 14) : m.start()]):
            marks.append((m.start(), (int(m.group(1) or m.group(2) or m.group(4)) + 2000, 4)))
    best_d, best_k = None, None
    for pos, kind in marks:
        if pos >= limit:
            continue
        d = 0 if a <= pos < b else (a - pos if pos < a else pos - b)
        if best_d is None or d < best_d or (d == best_d and kind == "quarter"):
            best_d, best_k = d, kind
    return best_k


def outcomes(docs: list[dict], fy_start: int, fiscal_label) -> list[dict]:
    """[{metric, cc, fy, quarters, value, quote, page, url, call, source}] from the calls read."""
    out = []
    for d in docs:
        qend: date = d["qend"]
        call_fy = _fy_of(qend, fy_start)
        qn = int(fiscal_label(qend, fy_start)[1])
        ss = gd.sentences(d["pages"])
        mgmt = gd.management_only(ss)
        for (page, s), is_mgmt in zip(ss, mgmt, strict=True):
            if not is_mgmt or "?" in s or not re.search(r"\d", s):
                continue
            result = VS_GUIDANCE.sub("", s)  # keep the result, drop "compared to our guidance of …"
            if FUTURE.search(result) or not OUTCOME.search(result) or gd.SKIP_OUTCOME.search(result):
                continue
            years = {
                int(m.group(1) or m.group(2) or m.group(4)) + 2000
                for m in gd.FY.finditer(result)
                if not PERIOD_BEFORE.search(result[max(0, m.start() - 14) : m.start()])
            }
            if len(years) > 1:
                continue  # "FY25 … in FY26 and H1 of FY27 … 21%": which year? don't guess
            for p in gd.pairs(result):
                if p["unit"] != "%" or p["scope"] == "segment" or p["metric"] in ("capex", "other"):
                    continue
                if not p["prefix"]:
                    gap = PERIOD_TOKEN.sub(" ", result[p["kw"][1] : p["at"]])
                    if len(gap) > 35 or re.search(r"\d|\band\b|\bwhile\b|[,;]", gap):
                        continue  # the number must sit right after its metric word
                span_a = min(p["kw"][0], p["at"])
                num_end = m.end() if (m := gd.NUMSPAN.match(result, p["at"])) else p["at"] + 1
                nxt = re.search(r"\d", result[num_end:])
                span_b = num_end + (nxt.start() if nxt else len(result) - num_end)
                phrase = result[span_a:span_b]  # metric word … number … up to the next number
                period = _nearest_period(result, span_a, num_end, span_b, qn, call_fy)
                if period == "quarter":
                    continue
                if period is None:
                    if p["metric"] in STOCK_METRICS and qn == 4 and YOY.search(phrase):
                        period = (call_fy, 4)  # a balance's YoY at year end is the year's growth
                    else:
                        continue
                fy, n = period
                if fy > call_fy:
                    continue
                near = phrase
                if p["low"] != p["high"]:
                    continue  # a reported result is one number, not a band
                out.append(
                    {
                        "metric": p["metric"],
                        "cc": bool(CC.search(near)),
                        "fy": fy,
                        "quarters": n,
                        "value": p["low"],
                        "quote": s,
                        "page": page,
                        "url": d["url"],
                        "call": d["label"],
                        "source": d.get("source") or "NSE",
                        "filed": str(d["filed_at"]),
                    }
                )
    return out


def best(reported: list[dict], metric: str, fy: int, cc: bool | None = None) -> dict | None:
    """The company's figure for (metric, fy): full year beats year to date; a later call beats an
    earlier one; for revenue growth, constant currency and rupee figures never stand in for each
    other."""
    xs = [r for r in reported if r["metric"] == metric and r["fy"] == fy and (cc is None or r["cc"] == cc)]
    if not xs:
        return None
    r = max(xs, key=lambda r: (r["quarters"], r["filed"]))
    return {
        "value": r["value"],
        "unit": "%",
        "span": "FY" if r["quarters"] == 4 else f"{r['quarters']}Q YTD",
        "quarters": r["quarters"],
        "basis": "company-reported" + (", constant currency" if r["cc"] else ""),
        "source": {
            "quote": r["quote"],
            "page": r["page"],
            "url": r["url"],
            "call": r["call"],
            "from": r["source"],
        },
    }
