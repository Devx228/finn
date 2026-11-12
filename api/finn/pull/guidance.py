"""Guidance extraction from earnings-call transcripts (pull side).

Cheap-first: code selects the few sentences that can carry guidance (management remarks with a
number near a forward-looking word) so the model reads ~5k characters, not 100k. The BULK model
structures them; code then keeps an item only if its quote appears in the transcript verbatim
(after whitespace normalisation). The model never computes or compares numbers.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from finn.llm.router import Router

PROMPT_VERSION = "guidance-v2"
MAX_CHARS = 6000
CUE = re.compile(
    r"guidance|guiding|guide[ds]? |we expect|we are expecting|we anticipate|outlook|target(?:ing)?|"
    r"aspir|we will (?:grow|deliver|achieve)|should be (?:in|around|between)|in the range of|"
    r"band|capex|capital expenditure|we aim|we plan to invest",
    re.I,
)
NUM = re.compile(r"\d")
NOISE = re.compile(r"External Document ©.*?\d+\s+|Page \d+ of \d+", re.I)

Metric = Literal[
    "revenue_growth",
    "revenue",
    "operating_margin",
    "ebitda_margin",
    "pat_growth",
    "capex",
    "aum_growth",
    "credit_cost",
    "other",
]


class Item(BaseModel):
    metric: Metric
    label: str = Field(description="short name as management says it, e.g. 'revenue growth (cc)'")
    period: str | None = Field(default=None, description="e.g. FY27, H2 FY27, Q3 FY27, FY28")
    low: float | None = None
    high: float | None = None
    unit: str | None = Field(default=None, description="% or ₹ cr or bps etc.")
    direction: Literal["new", "raised", "lowered", "maintained", "unclear"] = "unclear"
    quote: str = Field(description="the exact sentence from the text, copied verbatim")


class Extraction(BaseModel):
    items: list[Item]


SYSTEM = (
    "You read excerpts from an Indian listed company's earnings-call transcript. Extract only "
    "explicit forward-looking guidance given by MANAGEMENT on headline numbers: revenue or its "
    "growth, operating/EBIT or EBITDA margin, profit growth, capex, AUM/loan growth, credit cost. "
    "Ignore analysts' questions, past results, attrition, tax rate and anything not a target. "
    "For each item give metric, a short label, the period it covers, low and high (equal if a "
    "single number; numbers only, no % sign), unit, whether it is new/raised/lowered/maintained "
    "versus before, and the exact sentence as quote (copy it verbatim from the text). "
    'Return JSON {"items": [...]}. Return {"items": []} if there is none.'
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def sentences(pages: list[str]) -> list[tuple[int, str]]:
    out = []
    for i, p in enumerate(pages):
        p = NOISE.sub(" ", p)
        for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", p)):
            if 20 <= len(s) <= 600:
                out.append((i + 1, s.strip()))
    return out


def select(pages: list[str]) -> tuple[str, list[tuple[int, str]]]:
    """Management sentences with a cue word and a number, plus the next sentence for context."""
    ss = sentences(pages)
    keep: list[int] = []
    for i, (_, s) in enumerate(ss):
        if s.endswith("?") or not CUE.search(s) or not NUM.search(s):
            continue
        for j in (i, i + 1):
            if j < len(ss) and j not in keep and not ss[j][1].endswith("?"):
                keep.append(j)
    chosen, total = [], 0
    for j in keep:
        if total + len(ss[j][1]) > MAX_CHARS:
            break
        chosen.append(ss[j])
        total += len(ss[j][1]) + 1
    return "\n".join(s for _, s in chosen), chosen


def locate(quote: str, chosen: list[tuple[int, str]], full_norm: str) -> int | None:
    """Page number if the quote is verbatim in the transcript; None if it isn't (dropped)."""
    q = _norm(quote).strip(" .\"'")
    if len(q) < 15 or q not in full_norm:
        return None
    for page, s in chosen:
        if q[:40] in _norm(s):
            return page
    return 0


NUMSPAN = re.compile(
    r"(?:between\s+)?(?P<lo>-?\d+(?:\.\d+)?)\s*(?:%|percent|per cent)?\s*(?:to|-|–)\s*"
    r"(?P<hi>-?\d+(?:\.\d+)?)\s*(?P<u>%|percent|per cent|bps|basis points)"
    r"|(?:rs\.?|₹|inr)\s*(?P<cr>\d[\d,]*(?:\.\d+)?)\s*(?P<cru>crores?|cr|billion|bn)\b"
    r"|(?P<one>-?\d+(?:\.\d+)?)\s*(?P<ou>%|percent|per cent|bps|basis points)",
    re.I,
)
# Order matters: the more specific phrase claims its position first.
METRIC_KEYS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ebitda margin|ebitda", re.I), "ebitda_margin"),
    (re.compile(r"net interest margin|\bnim\b", re.I), "nim"),
    (re.compile(r"operating margin|ebit margin|\bmargins?\b", re.I), "operating_margin"),
    (re.compile(r"credit cost", re.I), "credit_cost"),
    (
        re.compile(
            r"\baum(?: growth)?\b|loan (?:book )?growth|loan book|book growth|disbursements?(?: growth)?",
            re.I,
        ),
        "aum_growth",
    ),
    (re.compile(r"cost[- ]to[- ]income", re.I), "cost_to_income"),
    (re.compile(r"\broa\b", re.I), "roa"),
    (re.compile(r"\broe\b", re.I), "roe"),
    (re.compile(r"capex|capital expenditure", re.I), "capex"),
    (
        re.compile(r"revenue growth|revenue|top[- ]?line(?: growth)?|\bgrowth\b|\bgrow\b", re.I),
        "revenue_growth",
    ),
]
COMPANY_WIDE = re.compile(
    r"\b(our|overall|company|consolidated|revenue|top ?line|we|annual|business)\b[^,;]*$", re.I
)
RULE_CUE = re.compile(
    r"guidance|guiding|guide |we expect|expected to|outlook|target|aspire|in the range of|we will|"
    r"we are confident|we aim",
    re.I,
)
SKIP = re.compile(
    r"tax rate|attrition|utili[sz]ation|headcount|dividend|payout|last year we|"
    r"(percentage|%|per ?cent) of (the )?revenue|subcontract|nine.month basis|we are now at|this quarter|"
    r"we (have )?delivered|\bin q[1-4]\b|ended at|as against|against (the|our) guidance|"
    r"versus (the|our) guidance|"
    r"you('re| are) guiding|your guidance|you (have )?guided|you said|what you|per month|\bvs\.? |"
    r"\bgrew\b|in line with|within the|you had|you mentioned|that you|\bmiss|closer to|we may|"
    r"may be|if we are able|in a bad year",
    re.I,
)
FY = re.compile(r"\b(?:FY|financial year|fiscal(?: year)?)\s?'?(?:20)?(\d{2})\b|\b20(\d{2})-(\d{2})\b", re.I)


def _fy(text: str, call_fy: int) -> str:
    m = FY.search(text)
    if m:
        y = int(m.group(1)) if m.group(1) else int(m.group(3))
        return f"FY{y:02d}"
    if re.search(r"next (fiscal |financial )?year", text, re.I):
        return f"FY{(call_fy + 1) % 100:02d}"
    return f"FY{call_fy % 100:02d}"


def _direction(low: str) -> str:
    if re.search(r"revis\w* (down|lower)|lower(ed)? (our|the)|\bcut\b|reduc", low):
        return "lowered"
    if re.search(r"revis\w* up|\brais|increas\w* (our|the) guidance", low):
        return "raised"
    if re.search(r"remain|maintain|retain|reiterat|unchanged|same", low):
        return "maintained"
    return "unclear"


def rule_items(chosen: list[tuple[int, str]], call_fy: int) -> list[dict]:
    """High-precision rules: each metric keyword in a guidance sentence takes the first number
    after it and before the next keyword, so 'AUM growth of 20–25%, NIM of 12.8–13.2%, credit
    cost of 3–4%' yields three items, each with its own band."""
    out, seen = [], set()
    for page, s in chosen:
        if "?" in s or not RULE_CUE.search(s) or SKIP.search(s):
            continue
        hits: list[tuple[int, int, str]] = []
        taken: list[tuple[int, int]] = []
        for rx, metric in METRIC_KEYS:
            for m in rx.finditer(s):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                hits.append((m.start(), m.end(), metric))
        hits.sort()
        nums = list(NUMSPAN.finditer(s))
        for i, (start, end, metric) in enumerate(hits):
            word = s[start:end].lower()
            if (
                metric == "revenue_growth"
                and word in ("growth", "grow")
                and not COMPANY_WIDE.search(s[max(0, start - 30) : start])
            ):
                continue  # "microfinance growth", "automotive to grow": a segment, not the company
            nxt = hits[i + 1][0] if i + 1 < len(hits) else len(s)
            seg = [x for x in nums if end <= x.start() < nxt]
            # "revised from 1.5% to 3% to 1% to 2%": after "from", the last band is the new one
            n = (seg[-1] if " from " in s[end : seg[0].start()].lower() else seg[0]) if seg else None
            if n is None:
                continue
            if n.group("cr"):
                v = float(n.group("cr").replace(",", ""))
                v *= 100 if n.group("cru").lower() in ("billion", "bn") else 1
                lo = hi = v
                unit = "₹ cr"
                if metric == "revenue_growth":
                    metric = "revenue"
            elif n.group("lo"):
                lo, hi = float(n.group("lo")), float(n.group("hi"))
                unit = "bps" if n.group("u").lower().startswith("b") else "%"
            else:
                lo = hi = float(n.group("one"))
                unit = "bps" if n.group("ou").lower().startswith("b") else "%"
            if metric == "capex" and unit != "₹ cr":
                continue
            if metric != "capex" and metric != "revenue" and unit == "₹ cr":
                continue
            if lo > hi:
                lo, hi = hi, lo
            key = (metric, lo, hi)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "metric": metric,
                    "label": metric.replace("_", " "),
                    "period": _fy(s, call_fy),
                    "low": lo,
                    "high": hi,
                    "unit": unit,
                    "direction": _direction(s.lower()),
                    "quote": s,
                    "page": page,
                    "by": "rules",
                }
            )
    return out


def extract(router: Router | None, pages: list[str], call_fy: int) -> tuple[list[dict], dict]:
    """Rules first; the BULK model adds what rules miss. Every kept quote is verbatim."""
    text, chosen = select(pages)
    if not text:
        return [], {"selected_chars": 0, "rules": 0, "model": 0, "dropped": 0}
    items = rule_items(chosen, call_fy)
    seen = {(i["metric"], i["low"], i["high"]) for i in items}
    n_rules, n_model, dropped, model = len(items), 0, 0, None
    if router is not None:
        try:
            res = router.call("BULK", "extract_guidance", PROMPT_VERSION, SYSTEM, text, Extraction)
            model = res.model
            full = _norm(" ".join(NOISE.sub(" ", p) for p in pages))
            for it in res.data.items:  # type: ignore[attr-defined]
                page = locate(it.quote, chosen, full)
                if (
                    page is None
                    or (it.low is None and it.high is None)
                    or SKIP.search(it.quote)
                    or "?" in it.quote
                ):
                    dropped += 1
                    continue
                key = (it.metric, it.low, it.high)
                if key in seen or any(_norm(i["quote"]) == _norm(it.quote) for i in items):
                    continue
                seen.add(key)
                d = it.model_dump()
                if d["metric"] == "revenue" and d.get("unit") == "%":
                    d["metric"] = "revenue_growth"
                    if ("revenue_growth", it.low, it.high) in seen:
                        continue
                d["period"] = _fy(it.quote, call_fy) if FY.search(it.quote) else _fy(it.period or "", call_fy)
                items.append({**d, "page": page or None, "by": "model"})
                n_model += 1
        except Exception as e:  # model down: rules-only result is still correct, just thinner
            model = f"unavailable: {e.__class__.__name__}"
    return items, {
        "selected_chars": len(text),
        "rules": n_rules,
        "model": n_model,
        "dropped": dropped,
        "model_name": model,
    }
