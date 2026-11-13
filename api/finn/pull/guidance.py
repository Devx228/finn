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

PROMPT_VERSION = "guidance-v3"
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
    "segment_revenue",
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
    scope: Literal["company", "segment"] = Field(
        default="company", description="segment if the number is for one business/segment only"
    )
    by_management: bool = Field(default=True, description="false if an analyst said it")
    future: bool = Field(default=True, description="false if it is a result already achieved")
    confidence: Literal["high", "medium", "low"] = "medium"
    quote: str = Field(description="the exact sentence from the text, copied verbatim")


class Extraction(BaseModel):
    items: list[Item]


SYSTEM = (
    "You read excerpts from an Indian listed company's earnings-call transcript. Extract only "
    "explicit forward-looking numeric guidance given by MANAGEMENT on headline numbers: revenue or "
    "its growth, operating/EBIT or EBITDA margin, profit growth, capex, AUM/loan growth, credit "
    "cost. A target for one business or segment uses metric segment_revenue (revenue) or keeps its "
    "metric with scope 'segment'. Do NOT extract: analysts' questions or their paraphrases of "
    "guidance, results already achieved, tax rate, headcount, dividends, impacts or bridges "
    "('will impact margins by 60 bps'), market-size or broker estimates. "
    "For each item give metric, a short label, the period it covers, low and high (equal if a "
    "single number; numbers only, no % sign), unit, whether it is new/raised/lowered/maintained "
    "versus before, scope, by_management, future, your confidence that this is real forward "
    "guidance, and the exact sentence as quote (copy it verbatim from the text). "
    'Return JSON {"items": [...]}. Return {"items": []} if there is none.'
)

# A model item must name its metric in its own quote (code check, not the model's word).
METRIC_WORDS = {
    "revenue_growth": r"revenue|growth|grow|top ?line|sales",
    "revenue": r"revenue|sales|top ?line|turnover",
    "segment_revenue": r"revenue|sales|top ?line|turnover",
    "operating_margin": r"margin|ebit",
    "ebitda_margin": r"ebitda|margin",
    "pat_growth": (
        r"(?:profit|\bpat\b|earnings)\W+(?:\w+\W+){0,2}grow"
        r"|grow\w*\W+(?:\w+\W+){0,2}(?:profit|\bpat\b|earnings)"
    ),
    "capex": r"capex|capital expenditure|invest|spend",
    "aum_growth": r"\baum\b|loan|book|disburs|advances|asset",
    "credit_cost": r"credit cost|provision",
}


def _numbers(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]


def doubt(it: Item) -> str | None:
    """Why a model item is not trusted (None = keep). Precision over volume."""
    q = it.quote
    if not (it.by_management and it.future):
        return "not forward-looking management guidance"
    if it.confidence != "high":
        return f"model confidence {it.confidence}"
    if it.metric == "other" or it.metric not in METRIC_WORDS:
        return "metric outside the tracked set"
    if not re.search(METRIC_WORDS[it.metric], q, re.I):
        return "metric not named in the quote"
    nums = _numbers(q)
    for v in [x for x in (it.low, it.high) if x is not None]:
        if not any(abs(v - n) < 1e-6 or abs(v - n * 100) < 1e-6 for n in nums):
            return f"{v:g} not in the quote"
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


PAGE_HEAD = re.compile(r"^.{0,120}?Page \d+ of \d+\s*", re.I)


def joined(pages: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """The transcript as one string (headers and page furniture removed) + (offset, page) starts."""
    text, starts = "", []
    for i, p in enumerate(pages):
        p = re.sub(r"\s+", " ", p).strip()
        p = NOISE.sub(" ", PAGE_HEAD.sub("", p)).strip()
        starts.append((len(text), i + 1))
        text += p + " "
    return text, starts


def sentences(pages: list[str]) -> list[tuple[int, str]]:
    """Sentences across the whole transcript (a sentence may run over a page break), each tagged
    with the page it starts on. Running page headers are dropped so they don't split a sentence."""
    text, starts = joined(pages)
    out, pos = [], 0
    for s in re.split(r"(?<=[.!?])\s+", text):
        page = max(pg for off, pg in starts if off <= pos) if starts else 1
        pos += len(s) + 1
        s = s.strip()
        if 20 <= len(s) <= 600:
            out.append((page, s))
    return out


SPEAKER = re.compile(r"^((?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?)?\s*[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,3}):\s")
ANALYST = re.compile(
    r"(?:question|questions) (?:is |comes |come )?from (?:the )?line of (?:Mr\.?|Ms\.?|Mrs\.?)?\s*"
    r"([A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){0,2})"
)


def management_only(ss: list[tuple[int, str]]) -> list[bool]:
    """Per sentence: True unless an analyst or the moderator is speaking. Speakers come from
    "Name:" tags; analysts are the names the moderator introduces ("question from the line of X")."""
    analysts = {m.group(1).strip().lower() for _, s in ss for m in ANALYST.finditer(s)}
    out, current = [], ""
    for _, s in ss:
        m = SPEAKER.match(s)
        if m:
            current = re.sub(r"^(?:mr|ms|mrs|dr)\.?\s*", "", m.group(1).strip().lower())
        out.append(
            not (current == "moderator" or any(current and current in a or a in current for a in analysts))
        )
    return out


def select(pages: list[str]) -> tuple[str, list[tuple[int, str]]]:
    """Management sentences with a cue word and a number, plus the next sentence for context."""
    ss = sentences(pages)
    mgmt = management_only(ss)
    keep: list[int] = []
    for i, (_, s) in enumerate(ss):
        if not mgmt[i] or s.endswith("?") or not CUE.search(s) or not NUM.search(s):
            continue
        for j in (i, i + 1):
            if j < len(ss) and j not in keep and mgmt[j] and not ss[j][1].endswith("?"):
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
    r"|(?:rs\.?|₹|inr)\s*(?P<crlo>\d[\d,]*(?:\.\d+)?)\s*(?:crores?\s*)?(?:to|-|–|and)\s*(?:rs\.?|₹|inr)?\s*"
    r"(?P<crhi>\d[\d,]*(?:\.\d+)?)\s*(?P<crru>crores?|cr|billion|bn)\b"
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
SEGMENT = re.compile(
    r"segment|division|vertical|subsidiar|\bbusiness(?:es)?\b|\bboth\b|\bunit\b|\bplant\b", re.I
)
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
    r"may be|if we are able|in a bad year|you have told|you told|you have said|\btcv\b|"
    r"order (?:intake|inflow)|bookings|it was just|was just|additional|incremental|"
    r"from (?:that|this|the) (?:one |mega |large )?deal|from one deal|contribut|run[- ]?rate|"
    r"(?:first|second) half|television|interview|\banother\b|remaining|balance of|"
    r"over the previous year|over last year",
    re.I,
)
FY = re.compile(
    r"\bFY\s?'?(?:20)?\d{2}\s?[-–]\s?(?:20)?(\d{2})\b"  # "FY25-26" is FY26
    r"|\b(?:FY|financial year|fiscal(?: year)?)\s?'?(?:20)?(\d{2})\b|\b20(\d{2})-(\d{2})\b",
    re.I,
)
# No single year to hold it to: an aspiration, or a total over several years.
OPEN_ENDED = re.compile(
    r"over a period of time|aspiration|aspirational|aspire|medium[- ]term|long[- ]term|"
    r"over the next (?:few|\d+|two|three|four|five) years|across these \w+ years|"
    r"in the next (?:few|\d+|two|three|four|five) years|total (?:spend|capex|investment)|cumulative|"
    r"in a good time|through[- ]the[- ]cycle|steady[- ]state|normali[sz]ed|over the cycle",
    re.I,
)
MEDIUM_TERM = "medium term"


YEARISH = re.compile(r"this year|next year|current year|for the year|this fiscal|full year|annual", re.I)


# A total spread over several years: never one year's number, even if a year is named.
MULTI_YEAR = re.compile(
    r"total (?:spend|capex|investment)|total \w+ of|cumulative|across these \w+ years|"
    r"over the next (?:few|\d+|two|three|four|five) years",
    re.I,
)


def _fy(text: str, call_fy: int) -> str:
    if MULTI_YEAR.search(text):
        return MEDIUM_TERM
    m = FY.search(text)
    if m:
        y = int(m.group(1) or m.group(2) or m.group(4))
        return f"FY{y:02d}"
    if OPEN_ENDED.search(text):
        return MEDIUM_TERM
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
        # "18%-20% AUM growth, 4.2%-4.5% ROA": a number right before a metric word is that
        # metric's, and no other keyword may take it.
        prefix: dict[int, re.Match[str]] = {}
        for h_start, _e, _m in hits:
            before = [x for x in nums if 0 <= h_start - x.end() <= 2 and not s[x.end() : h_start].strip()]
            if before:
                prefix[h_start] = before[-1]
        claimed = {id(x) for x in prefix.values()}
        for i, (start, end, metric) in enumerate(hits):
            word = s[start:end].lower()
            if (
                metric == "revenue_growth"
                and word in ("growth", "grow")
                and not COMPANY_WIDE.search(s[max(0, start - 30) : start])
            ):
                continue  # "microfinance growth", "automotive to grow": a segment, not the company
            nxt = hits[i + 1][0] if i + 1 < len(hits) else len(s)
            seg = [x for x in nums if end <= x.start() < nxt and id(x) not in claimed]
            # "revised from 1.5% to 3% to 1% to 2%": after "from", the last band is the new one
            n = (seg[-1] if " from " in s[end : seg[0].start()].lower() else seg[0]) if seg else None
            n = prefix.get(start, n)
            if n is None:
                continue
            if n.group("cr") or n.group("crlo"):
                big = (n.group("cru") or n.group("crru")).lower() in ("billion", "bn")
                vals = [n.group("cr")] if n.group("cr") else [n.group("crlo"), n.group("crhi")]
                lo, hi = (float(x.replace(",", "")) * (100 if big else 1) for x in (vals[0], vals[-1]))
                unit = "₹ cr"
                if metric == "revenue_growth":
                    # a ₹ figure for one business is not company revenue: never score it as such
                    metric = "segment_revenue" if SEGMENT.search(s) else "revenue"
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
                    "period": MEDIUM_TERM
                    if metric == "capex" and not (FY.search(s) or YEARISH.search(s))
                    else _fy(s, call_fy),
                    "low": lo,
                    "high": hi,
                    "unit": unit,
                    "direction": _direction(s.lower()),
                    "quote": s,
                    "page": page,
                    "scope": "segment" if unit == "₹ cr" and SEGMENT.search(s) else "company",
                    "by": "rules",
                }
            )
    return out


def extract(
    router: Router | None,
    pages: list[str],
    call_fy: int,
    tier: str = "EXTRACT",
    strict: bool = True,
    use_rules: bool = True,
) -> tuple[list[dict], dict]:
    """Rules first (positional, high precision: each metric keyword takes its own number); the
    model adds what rules can't read (no keyword next to the number, segment scope, a sentence
    that runs on) but never overrides a rule item from the same sentence. Every kept quote is
    verbatim; with `strict`, any model item the confidence check doubts is dropped (reason
    recorded)."""
    text, chosen = select(pages)
    if not text:
        return [], {"selected_chars": 0, "rules": 0, "model": 0, "dropped": 0}
    items: list[dict] = rule_items(chosen, call_fy) if use_rules else []
    n_rules, n_model, dropped, model = len(items), 0, 0, None
    reasons: dict[str, int] = {}

    def conflicts(m: Item) -> bool:
        q = _norm(m.quote)
        for r in items:
            rq = _norm(r["quote"])
            same_sentence = q in rq or rq in q
            same_band = (r["low"], r["high"]) == (m.low, m.high) or m.high in (r["low"], r["high"])
            if (same_sentence and (r["metric"] == m.metric or same_band)) or (
                r["metric"] == m.metric and (r["low"], r["high"]) == (m.low, m.high)
            ):
                return True
        return False

    if router is not None:
        try:
            res = router.call(tier, "extract_guidance", PROMPT_VERSION, SYSTEM, text, Extraction)
            model = res.model
            full = _norm(joined(pages)[0])
            for it in res.data.items:  # type: ignore[attr-defined]
                if it.metric == "revenue" and it.scope == "segment":
                    it.metric = "segment_revenue"
                if it.metric == "revenue" and (it.unit or "").strip() == "%":
                    it.metric = "revenue_growth"
                page = locate(it.quote, chosen, full)
                why = (
                    "quote not verbatim"
                    if page is None
                    else "no number"
                    if it.low is None and it.high is None
                    else "skip pattern / question"
                    if SKIP.search(it.quote) or "?" in it.quote
                    else (doubt(it) if strict else None)
                )
                if why:
                    dropped += 1
                    reasons[why] = reasons.get(why, 0) + 1
                    continue
                if it.low is None or it.high is None:
                    it.low = it.high = it.low if it.low is not None else it.high
                if conflicts(it):
                    continue  # a rule already read this sentence's number
                d = it.model_dump()
                if d.get("unit") and re.search(r"cr|crore|inr|rs|₹", d["unit"], re.I):
                    d["unit"] = "₹ cr"
                d["period"] = (
                    _fy(it.quote, call_fy)
                    if FY.search(it.quote) or OPEN_ENDED.search(it.quote)
                    else _fy(it.period or "", call_fy)
                )
                if d["metric"] == "capex" and not (FY.search(it.quote) or YEARISH.search(it.quote)):
                    d["period"] = MEDIUM_TERM  # a project's capex with no year is not a year's plan
                items.append({**d, "page": page or None, "by": "model"})
                n_model += 1
        except Exception as e:  # model down: rules-only result is still correct, just thinner
            model = f"unavailable: {e.__class__.__name__}: {str(e)[:160]}"
    return items, {
        "selected_chars": len(text),
        "rules": n_rules,
        "model": n_model,
        "dropped": dropped,
        "drop_reasons": reasons,
        "model_name": model,
    }
