"""Research view for any NSE company (pull side), grounded only in primary sources:
quarterly numbers from the company's XBRL results filings and guidance from its own earnings-call
transcripts. Code computes every number and every verdict; the model only structures guidance
sentences (and only verbatim quotes survive).

The headline output is "promised vs delivered": each guided metric's band across the last four
calls (raised / held / cut, computed by comparing bands, not by reading adjectives), checked
against what the filings later reported.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.llm.router import Router
from finn.pull import guidance as gd
from finn.pull import reported as reported_mod
from finn.pull import transcripts as tr
from finn.push.pipeline import _quarter_facts
from finn.push.results import CR, fiscal_label, metrics
from finn.sources.nse import NSE

METRIC_SHORT = {
    "revenue_growth": "Rev. growth",
    "revenue": "Revenue",
    "operating_margin": "Op. margin",
    "ebitda_margin": "EBITDA margin",
    "pat_growth": "Profit growth",
    "capex": "Capex",
    "aum_growth": "AUM growth",
    "credit_cost": "Credit cost",
    "nim": "NIM",
    "roa": "ROA",
    "roe": "ROE",
    "cost_to_income": "Cost/income",
}
METRIC_LABEL = {
    "revenue_growth": "Revenue growth",
    "revenue": "Revenue",
    "operating_margin": "Operating margin",
    "ebitda_margin": "EBITDA margin",
    "pat_growth": "Profit growth",
    "capex": "Capex",
    "aum_growth": "AUM / loan growth",
    "credit_cost": "Credit cost",
    "nim": "Net interest margin",
    "roa": "Return on assets",
    "roe": "Return on equity",
    "cost_to_income": "Cost-to-income",
    "segment_revenue": "Segment revenue",
    "other": "Other",
}


def _fy_of(d: date, fy_start: int) -> int:
    return d.year + (1 if fy_start != 1 and d.month >= fy_start else 0)


def quarters(conn: Connection, company_id: int, fmt: str) -> tuple[list[dict], int]:
    periods, fy_start = _quarter_facts(conn, company_id)
    by_end: dict[date, object] = {}
    for (end, basis), p in sorted(periods.items()):
        if basis == "consolidated" or end not in by_end:
            by_end[end] = p
    out = []
    for end in sorted(by_end):
        p = by_end[end]
        m = metrics(fmt, p.facts)  # type: ignore[attr-defined]
        da = p.facts.get("DepreciationDepletionAndAmortisationExpense")  # type: ignore[attr-defined]
        rev = m.get("revenue")
        ebitda = m.get("ebitda")
        ebit = ebitda - da if ebitda is not None and da is not None else None

        def cr(x: Decimal | None) -> float | None:
            return None if x is None else round(float(x / CR), 1)

        def mg(x: Decimal | None, rev: Decimal | None = rev) -> float | None:
            return None if x is None or not rev else round(float(x / rev * 100), 1)

        out.append(
            {
                "end": str(end),
                "label": fiscal_label(end, fy_start),
                "fy": _fy_of(end, fy_start),
                "basis": p.basis,  # type: ignore[attr-defined]
                "revenue": cr(rev),
                "ebitda": cr(ebitda),
                "ebit": cr(ebit),
                "pat": cr(m.get("pat")),
                "nii": cr(m.get("nii")),
                "ebitda_margin": mg(ebitda),
                "ebit_margin": mg(ebit),
                "pat_margin": mg(m.get("pat")),
                "xbrl": p.xbrl_url,  # type: ignore[attr-defined]
            }
        )
    # YoY for revenue and PAT (same basis only)
    idx = {q["end"]: q for q in out}
    for q in out:
        e = date.fromisoformat(q["end"])
        prev = idx.get(str(date(e.year - 1, e.month, e.day)))
        for k in ("revenue", "pat"):
            a, b = q[k], prev[k] if prev and prev["basis"] == q["basis"] else None
            q[f"{k}_yoy"] = round((a / b - 1) * 100, 1) if a is not None and b and b > 0 else None
    return out, fy_start  # all cached quarters: actuals need the prior year; display trims


def fy_actual(qs: list[dict], fy: int, metric: str) -> dict | None:
    """Full-year (4 quarters) or year-to-date actual for a guided metric. Revenue growth compares
    the same quarters a year earlier, so a YTD figure is comparable to a full-year band."""
    cur = [q for q in qs if q["fy"] == fy]
    prev = {q["label"][:2]: q for q in qs if q["fy"] == fy - 1}
    if not cur:
        return None
    n = len(cur)
    span = "FY" if n == 4 else f"{n}Q YTD"
    if metric == "revenue_growth":
        pairs = [(q["revenue"], prev.get(q["label"][:2], {}).get("revenue")) for q in cur]
        if any(a is None or b is None for a, b in pairs):
            return None
        a = sum(p[0] for p in pairs)  # type: ignore[misc]
        b = sum(p[1] for p in pairs)  # type: ignore[misc]
        return {
            "value": round((a / b - 1) * 100, 1),
            "unit": "%",
            "span": span,
            "quarters": n,
            "basis": "reported ₹ growth, consolidated",
        }
    if metric == "revenue":
        if n != 4 or any(q["revenue"] is None for q in cur):
            return None
        return {
            "value": round(sum(q["revenue"] for q in cur), 1),
            "unit": "₹ cr",
            "span": span,
            "quarters": n,
            "basis": "revenue from operations, consolidated",
        }
    if metric in ("operating_margin", "ebitda_margin"):
        k = "ebit" if metric == "operating_margin" else "ebitda"
        if any(q[k] is None or q["revenue"] is None for q in cur):
            return None
        v = sum(q[k] for q in cur) / sum(q["revenue"] for q in cur) * 100
        return {
            "value": round(v, 1),
            "unit": "%",
            "span": span,
            "quarters": n,
            "basis": f"{'EBIT' if k == 'ebit' else 'EBITDA'} ÷ revenue from the filings",
        }
    return None


# --- metrics checkable straight from the XBRL filings (balance sheet / cash flow / P&L) --------
def _facts(conn: Connection, cid: int, concepts: list[str]) -> dict[str, list[tuple]]:
    """{concept: [(start, end, value_cr, xbrl_url)]}, consolidated preferred per period."""
    rows = conn.execute(
        "SELECT x.concept, x.period_start, x.period_end, x.value, ff.basis, ff.xbrl_url FROM fin_facts x "
        "JOIN fin_filings ff ON ff.id = x.fin_filing_id WHERE ff.company_id = %s AND x.dims = '' "
        "AND x.concept = ANY(%s) ORDER BY ff.filed_at",
        (cid, concepts),
    ).fetchall()
    best: dict[tuple, tuple] = {}
    for c, s, e, v, basis, url in rows:
        k = (c, s, e)
        if k not in best or basis == "consolidated":
            best[k] = (s, e, float(v) / 1e7, url, basis)
    out: dict[str, list[tuple]] = defaultdict(list)
    for (c, _s, _e), t in best.items():
        out[c].append(t)
    return out


def _fy_bounds(fy: int, fy_start: int) -> tuple[date, date]:
    import calendar

    if fy_start == 1:
        return date(fy, 1, 1), date(fy, 12, 31)
    end_m = fy_start - 1
    return date(fy - 1, fy_start, 1), date(fy, end_m, calendar.monthrange(fy, end_m)[1])


def _months(s: date, e: date) -> int:
    return (e.year - s.year) * 12 + e.month - s.month + 1


def filing_actual(conn: Connection, cid: int, metric: str, fy: int, fy_start: int) -> dict | None:
    """Actual for capex / loan growth / credit cost / ROA / ROE, full year or
    year to date (annualised where the metric is a rate). Computed here, cited to the XBRL."""
    f = _facts(
        conn,
        cid,
        [
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "Loans",
            "ImpairmentOnFinancialInstruments",
            "ProfitLossForPeriod",
            "Assets",
            "Equity",
        ],
    )
    fs, fe = _fy_bounds(fy, fy_start)
    prior_end = date.fromordinal(fs.toordinal() - 1)

    def flow(concept: str) -> tuple[float, date, str] | None:
        """Longest period starting at the FY start, within the FY (FY or YTD)."""
        xs = [t for t in f.get(concept, []) if t[0] == fs and t[1] <= fe]
        if not xs:
            return None
        t = max(xs, key=lambda t: t[1])
        return t[2], t[1], t[3]

    def stock(concept: str, at: date) -> tuple[float, str] | None:
        xs = [t for t in f.get(concept, []) if t[0] is None and t[1] == at]
        return (xs[0][2], xs[0][3]) if xs else None

    def pack(value: float, end: date, unit: str, basis: str, url: str, annualised: bool = False) -> dict:
        n = _months(fs, end) // 3
        return {
            "value": round(value, 1),
            "unit": unit,
            "span": "FY" if n == 4 else f"{n}Q YTD" + (" annualised" if annualised else ""),
            "quarters": n,
            "basis": basis,
            "source": {"xbrl": url},
        }

    if metric == "capex":
        x = flow("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
        return (
            pack(x[0], x[1], "₹ cr", "purchase of property, plant & equipment (cash flow)", x[2])
            if x
            else None
        )
    if metric == "aum_growth":
        ends = sorted({t[1] for t in f.get("Loans", []) if t[0] is None and fs <= t[1] <= fe})
        if not ends:
            return None
        end = ends[-1]
        yago = date(end.year - 1, end.month, end.day)
        a, b = stock("Loans", end), stock("Loans", yago)
        if not a or not b or not b[0]:
            return None
        return pack(
            (a[0] / b[0] - 1) * 100,
            end,
            "%",
            f"loans on the balance sheet, YoY to {end:%b %Y} (AUM also includes off-book loans)",
            a[1],
        )
    rate = {
        "credit_cost": "ImpairmentOnFinancialInstruments",
        "roa": "ProfitLossForPeriod",
        "roe": "ProfitLossForPeriod",
    }
    if metric in rate:
        x = flow(rate[metric])
        if not x:
            return None
        denom_c = {"credit_cost": "Loans", "roa": "Assets", "roe": "Equity"}[metric]
        a, b = stock(denom_c, x[1]), stock(denom_c, prior_end)
        if not a or not b:
            return None
        k = 12 / _months(fs, x[1])
        v = x[0] * k / ((a[0] + b[0]) / 2) * 100
        what = {
            "credit_cost": "impairment on financial instruments ÷ average loans",
            "roa": "profit ÷ average total assets",
            "roe": "profit ÷ average equity",
        }[metric]
        return pack(v, x[1], "%", what, x[2], annualised=k != 1)
    return None


LOWER_BETTER = {"credit_cost"}
LENDER_METRICS = {"aum_growth", "credit_cost", "nim", "roa"}
LENDER_WORDS = re.compile(r"\bROA\b|\bNIM\b|loan book|credit cost|\bAUM\b|disbursement", re.I)
NOT_SCORED = "not scored"
# SPEC §10.3 (owner, 13 Nov): when the company reports the guided metric itself, that number is the
# actual. Our own figure from the filings is the actual only where the filing is unambiguous;
# for everything else it is shown as a cross-check and never decides a verdict.
COMPUTED_OK = {"revenue", "revenue_growth", "ebitda_margin"}


def run_rate(qs: list[dict], fy: int, metric: str, last: dict) -> str | None:
    """What the rest of the year needs for a still-open revenue band, from the filings
    (unambiguous metrics only): "Needs +14.8% YoY in the remaining 2 quarters (so far +11.4%)"."""
    cur = [q for q in qs if q["fy"] == fy and q["revenue"] is not None]
    prev = {q["label"][:2]: q for q in qs if q["fy"] == fy - 1 and q["revenue"] is not None}
    if not cur or len(cur) >= 4 or len(prev) < 4:
        return None
    done = {q["label"][:2] for q in cur}
    ytd, ytd_prev = sum(q["revenue"] for q in cur), sum(prev[k]["revenue"] for k in done if k in prev)
    rest_prev = sum(q["revenue"] for k, q in prev.items() if k not in done)
    left = 4 - len(cur)
    if not ytd_prev or not rest_prev:
        return None
    so_far = (ytd / ytd_prev - 1) * 100
    if metric == "revenue_growth" and last.get("unit") == "%":
        lo = ((ytd_prev + rest_prev) * (1 + last["low"] / 100) - ytd) / rest_prev * 100 - 100
        hi = ((ytd_prev + rest_prev) * (1 + last["high"] / 100) - ytd) / rest_prev * 100 - 100
        need = f"{lo:+.1f}%" if abs(hi - lo) < 0.05 else f"{lo:+.1f}% to {hi:+.1f}%"
        return f"Needs {need} YoY in the remaining {left} quarter{'s' * (left > 1)} (so far {so_far:+.1f}%)"
    if metric == "revenue" and last.get("unit") == "₹ cr":
        need_cr = last["low"] - ytd
        g = (need_cr / rest_prev - 1) * 100
        return (
            f"Needs ₹{need_cr:,.0f} cr in the remaining {left} quarter{'s' * (left > 1)} "
            f"({g:+.1f}% YoY; so far {so_far:+.1f}%)"
        )
    return None


def _fmt(a: dict) -> str:
    v = f"₹{a['value']:,.0f} cr" if a["unit"] == "₹ cr" else f"{a['value']}%"
    return f"{v} ({a['span']})"


def _computed(conn, cid, qs: list[dict], metric: str, fy: int, fy_start: int, last: dict) -> dict | None:
    if metric in FILING_METRICS:
        return filing_actual(conn, cid, metric, fy, fy_start) if conn is not None and cid else None
    a = fy_actual(qs, fy, metric)
    if a:
        a = {**a, "basis": "computed from the results filings: " + a["basis"]}
    return a


# cost-to-income is deliberately absent: the company's definition can't be rebuilt from XBRL lines
# (CREDITACC reported 34.1% where opex ÷ (income − finance costs) gives ~29%), so it isn't scored.
FILING_METRICS = {"capex", "aum_growth", "credit_cost", "roa", "roe"}


# "at least 20%", "north of 10%": a floor, met by anything at or above it
FLOOR = re.compile(
    r"at least|north of|more than|in excess of|upwards of|\bminimum\b|\bexceed|"
    r"\b(?:over|above)\s+(?:₹|rs\.?|inr)?\s?\d|\d\s*%?\s*(?:\+|plus\b(?!\s*/\s*minus|\s+or\s+minus))",
    re.I,
)
SUSPECT_GAP = 0.30  # guided vs actual this far apart: probably not the same thing


def verdict(
    actual: dict | None,
    low: float,
    high: float,
    final: bool,
    lower_better: bool = False,
    floor: bool = False,
) -> tuple[str, str]:
    """beat = clearly beyond the band in the good direction; delivered = within it (or meeting a
    floor); missed = short of it. Before the year ends: ahead / on track / behind."""
    if actual is None:
        return NOT_SCORED, "No actual for this period"
    v = actual["value"]
    slack = 0.05  # rounding only: reported figures carry one decimal
    band = f"{low:g}–{high:g}%" if low != high else f"{low:g}%"
    if floor and not lower_better and v >= low - slack:
        return ("delivered" if final else "on track"), f"{v}% vs at least {low:g}%"
    if v < low - slack:
        good = lower_better
        return (
            ("beat" if final else "ahead") if good else ("missed" if final else "behind")
        ), f"{v}% vs {band}"
    if v > high + slack:
        good = not lower_better
        return (
            ("beat" if final else "ahead") if good else ("missed" if final else "behind")
        ), f"{v}% vs {band}"
    return ("delivered" if final else "on track"), f"{v}% within {band}"


def _capex_verdict(act: dict, plan: float) -> tuple[str, str]:
    n = act["quarters"]
    spent = act["value"]
    if n == 4:
        ok = abs(spent / plan - 1) <= 0.15
        return ("delivered" if ok else "missed"), f"₹{spent:,.0f} cr spent vs ₹{plan:,.0f} cr planned"
    pace = spent / (plan * n / 4)
    return (
        "on track" if pace >= 0.75 else "behind",
        f"₹{spent:,.0f} cr spent in {n}Q ({spent / plan * 100:.0f}% of the ₹{plan:,.0f} cr plan)",
    )


MET = ("delivered", "beat")
# The first statement read already says it is a revision: the original is in a call not read.
REVISED = re.compile(r"\brevis|\bupward|\bdownward|\braise[ds]?\b|\bchanging our\b|\bnarrow", re.I)


def is_floor(p: dict) -> bool:
    """A floor word next to this point's own number ("in excess of ₹3,000 cr", "15% plus"), not
    anywhere in a quote that may carry a neighbouring sentence."""
    q = p.get("quote", "")
    lo = p["low"]
    forms = [f"{lo:,.0f}", f"{lo:.0f}", f"{lo:g}"] if lo == int(lo) else [f"{lo:g}"]
    idx = next((q.find(x) for x in forms if x in q), -1)
    win = q if idx < 0 else q[max(0, idx - 45) : idx + 25]
    return bool(FLOOR.search(win))


VERB = {"delivered": "met", "beat": "beat", "missed": "missed"}
REITERATE = re.compile(r"\b(?:retain|maintain|reiterat|reaffirm|stick to|stay with|remain)", re.I)


def _rev_verdict(a: float, p: dict) -> tuple[str, str]:
    lo, hi = p["low"], p["high"]
    floor = is_floor(p)
    band = f"₹{lo:,.0f} cr" if lo == hi else f"₹{lo:,.0f}–{hi:,.0f} cr"
    v = "missed" if a < lo * 0.98 else "delivered" if floor or a <= hi * 1.02 else "beat"
    return v, f"₹{a:,.0f} cr vs {band} guided"


def _judge(act: dict, p: dict, metric: str, lower: bool) -> tuple[str, str]:
    """The verdict of a full-year actual against one guidance point."""
    if metric == "capex":
        return _capex_verdict(act, p["high"])
    if metric == "revenue" and p.get("unit") == "₹ cr":
        return _rev_verdict(act["value"], p)
    return verdict(act, p["low"], p["high"], True, lower, is_floor(p))


def _bandtxt(p: dict) -> str:
    rupees = p.get("unit") == "₹ cr"
    f = (lambda x: f"₹{x:,.0f} cr") if rupees else (lambda x: f"{x:g}%")
    if is_floor(p):
        return f"{f(p['low'])}+"
    if p["low"] == p["high"]:
        return f(p["low"])
    return f"₹{p['low']:,.0f}–{p['high']:,.0f} cr" if rupees else f"{p['low']:g}–{p['high']:g}%"


def _position(a: float, p: dict) -> str | None:
    lo, hi = p["low"], p["high"]
    tol = 0.05 if p.get("unit") != "₹ cr" else 0.005 * lo
    if is_floor(p) or lo == hi or not (lo - tol <= a <= hi + tol):
        return None
    if abs(a - lo) <= tol:
        return "at the very bottom of the range"
    if abs(a - hi) <= tol:
        return "at the very top of the range"
    frac = (a - lo) / (hi - lo)
    return "in the lower half of the range" if frac < 0.5 else "in the upper half of the range"


def _line(first: dict, v1: str, last: dict, v2: str, act: dict, two: bool) -> str:
    """One line, in management's own qualifiers: 'Missed preliminary 18–20% outlook · met the
    lowered 14–18%, at the very bottom of the range'."""
    pos = _position(act["value"], last) if v2 == "delivered" else None
    q1 = f"{first['qualifier']} " if first.get("qualifier") else ""
    head = f"{VERB[v1]} {q1}{_bandtxt(first)} {first.get('noun') or 'guidance'}"
    if not two:
        return (head + (f", {pos}" if pos else "")).capitalize()
    mid1, mid2 = (first["low"] + first["high"]) / 2, (last["low"] + last["high"]) / 2
    moved = "lowered" if mid2 < mid1 else "raised" if mid2 > mid1 else "restated"
    q2 = f"{last['qualifier']} " if last.get("qualifier") else ""
    tail = f"{VERB[v2]} the {moved} {q2}{_bandtxt(last)}" + (f", {pos}" if pos else "")
    out = f"{head} · {tail}"
    return out[0].upper() + out[1:]


def pattern(trks: list[dict], calls_read: int = 0, calls_listed: int = 0) -> str | None:
    """The ledger's one-line count, from the computed counts only:
    '5 resolved · none met as first given · 1 met only after a cut · 4 missed, 2 of them even after
    a cut'."""
    res = [t for t in trks if t["resolved"]]
    if not res:
        return None
    n = len(res)
    unknown = sum(bool(t.get("first_is_revision")) for t in res)
    first_met = sum(t.get("verdict_first") in MET for t in res)
    cut_then_met = sum(
        t["verdict"] in MET and t.get("moved") == "lowered" and t.get("verdict_first") not in MET for t in res
    )
    revised_met = sum(t["verdict"] in MET and bool(t.get("first_is_revision")) for t in res)
    raised_beaten = sum(t["verdict"] == "beat" and t.get("moved") == "raised" for t in res)
    missed = sum(t["verdict"] == "missed" for t in res)
    missed_after_cut = sum(t["verdict"] == "missed" and t.get("moved") == "lowered" for t in res)
    parts = [f"{n} resolved"]
    if n - unknown:
        parts.append(f"{first_met or 'none'} met as first given")
    if cut_then_met:
        parts.append(f"{cut_then_met} met only after a cut")
    if raised_beaten:
        parts.append(f"{raised_beaten} beat a raised target")
    if revised_met:
        seen = f" ({calls_read} of {calls_listed})" if calls_listed else ""
        parts.append(f"{revised_met} met a revised target whose original is in a call not read{seen}")
    if missed:
        parts.append(
            f"{missed} missed"
            + (f", {missed_after_cut} of them even after a cut" if missed_after_cut else "")
        )
    return " · ".join(parts)


def _already_passed(qs: list[dict], metric: str, last: dict) -> float | None:
    """For a revenue level target: trailing-four-quarter revenue reported before the call that
    stated it. If that already met the target, the 'guidance' restates a goal already reached."""
    if metric != "revenue" or last.get("unit") != "₹ cr" or not last.get("call_date"):
        return None
    before = [q for q in qs if q["revenue"] is not None and str(q["end"]) < last["call_date"]]
    if len(before) < 4:
        return None
    ttm = sum(q["revenue"] for q in before[-4:])
    return ttm if ttm >= last["low"] else None


def _suspect(act: dict, last: dict, fy: int | None) -> bool:
    mid = (last["low"] + last["high"]) / 2
    if not mid or fy is None:
        return False
    if abs(act["value"] / mid - 1) <= SUSPECT_GAP:
        return False
    named = gd.FY.search(last["quote"])
    if named:
        y = int(named.group(1) or named.group(2) or named.group(4))
        if y == fy % 100:
            return False  # the quote names this exact year: the comparison is unambiguous
    return True


def tracks(
    calls: list[dict],
    qs: list[dict],
    fy_start: int,
    conn: Connection | None = None,
    cid: int | None = None,
    reported: list[dict] | None = None,
    lender: bool = False,
) -> list[dict]:
    series: dict[tuple[str, str], list[dict]] = defaultdict(list)
    quotes = [it["quote"].lower() for c in calls for it in c["items"]]
    # a company that guides revenue in constant currency does so every time, even when a
    # revision sentence doesn't repeat the words
    cc_company = any(
        ("constant currency" in q or " cc " in f" {q} ") and ("revenue" in q or "growth" in q) for q in quotes
    )
    uses_ebitda = any("ebitda" in q for q in quotes)
    for c in sorted(calls, key=lambda c: c["filed_at"]):
        best: dict[tuple[str, str], dict] = {}
        for it in c["items"]:
            if it.get("unit") == "bps" or it.get("low") is None:
                continue  # bps are changes, not levels; a chain never mixes units
            if not lender and (
                it["metric"] in LENDER_METRICS or LENDER_WORDS.search(it["quote"])
            ):  # a non-lender talking loan book / credit cost / NIM / ROA is talking about a subsidiary
                it = {**it, "scope": "segment"}
            if lender and it["metric"] == "revenue_growth":
                it = {**it, "metric": "aum_growth"}  # a lender's "growth" is loan-book growth
            if (
                uses_ebitda
                and it["metric"] == "operating_margin"
                and not re.search(r"operating|\bebit\b", it["quote"], re.I)
            ):
                it = {**it, "metric": "ebitda_margin"}  # "margins will be 15%" at an EBITDA reporter
            key = (it["metric"], it["period"])
            # one point per call per metric: prefer company-wide, then the model's structured read
            if key not in best or (best[key].get("scope") == "segment" and it.get("scope") != "segment"):
                best[key] = it
        for key, it in best.items():
            series[key].append(
                {
                    **it,
                    "call": c["label"],
                    "call_date": c["filed_at"][:10],
                    "url": c["url"],
                    "source": c.get("source", "NSE"),
                }
            )
    # A yearless "we retain our guidance of X" with exactly the band an open chain already carries
    # reiterates that chain (no new number, no guessed year).
    for (metric, period), pts in list(series.items()):
        if period != gd.NO_YEAR:
            continue
        keep = []
        for pt in pts:
            hosts = [
                k
                for k, v in series.items()
                if k[0] == metric
                and k[1].startswith("FY")
                and v
                and v[-1]["call_date"] < pt["call_date"]
                and (v[-1]["low"], v[-1]["high"]) == (pt["low"], pt["high"])
            ]
            if REITERATE.search(pt["quote"]) and len(hosts) == 1:
                series[hosts[0]].append({**pt, "period": hosts[0][1], "reiterates": True})
            else:
                keep.append(pt)
        if keep:
            series[(metric, period)] = keep
        else:
            del series[(metric, period)]
    # Verbal steers: an analyst's range that management explicitly confirmed or rejected, attached
    # to the chain carrying that range at the time.
    steer_map: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in calls:
        for st in c.get("steers") or []:
            m = "aum_growth" if lender and st["metric"] == "revenue_growth" else st["metric"]
            day = c["filed_at"][:10]
            hosts = [
                k
                for k, v in series.items()
                if (m is None or k[0] == m)
                and any(p["call_date"] <= day and (p["low"], p["high"]) == (st["low"], st["high"]) for p in v)
            ]
            if not hosts or len({k[0] for k in hosts}) > 1:
                continue  # no chain carries that range, or it fits more than one metric: don't guess
            fy_now = f"FY{_fy_of(date.fromisoformat(day), fy_start) % 100:02d}"
            host = fy_now if any(k[1] == fy_now for k in hosts) else None
            key = next((k for k in hosts if k[1] == host), hosts[0])
            steer_map[key].append({**st, "call": c["label"], "call_date": day, "url": c["url"]})
    latest_q = max((q["end"] for q in qs), default=None)
    last_fy_rev = None
    full = [q for q in qs if q["revenue"] is not None]
    if len(full) >= 4:
        last_fy_rev = sum(q["revenue"] for q in full[-4:])
    out = []
    for (metric, period), pts in series.items():
        if metric in ("other",):
            continue
        prev = None
        for p in pts:
            if prev is None:
                p["change"] = "first given"
            else:
                mid, pmid = (p["low"] + p["high"]) / 2, (prev["low"] + prev["high"]) / 2
                p["change"] = (
                    "raised"
                    if mid > pmid + 1e-9
                    else "cut"
                    if mid < pmid - 1e-9
                    else ("narrowed" if (p["high"] - p["low"]) < (prev["high"] - prev["low"]) else "held")
                )
            prev = p
        fy = int(period[2:]) + 2000 if period and period.startswith("FY") and period[2:].isdigit() else None
        last = pts[-1]
        cc_guided = cc_company and metric == "revenue_growth"
        segment = (
            metric == "segment_revenue"
            or any(p.get("scope") == "segment" for p in pts)
            or (
                metric == "revenue"
                and last.get("unit") == "₹ cr"
                and last_fy_rev
                and last["high"] < 0.5 * last_fy_rev
            )
        )
        act = None
        cross = None
        context = None
        lower = metric in LOWER_BETTER
        if segment:
            v, why = NOT_SCORED, "A target for one business; the filings report the company as a whole"
        elif fy is None:
            v, why = (
                "open-ended",
                (
                    "The quote names no year, so it can't be held to one; listed, not scored"
                    if period == gd.NO_YEAR
                    else "No year attached, so it never falls due; listed, not scored"
                ),
            )
        elif (passed := _already_passed(qs, metric, last)) is not None:
            v, why = (
                NOT_SCORED,
                (
                    f"Already reached when stated: revenue for the four quarters before the "
                    f"{last['call']} was ₹{passed:,.0f} cr, so this restates an old goal, not a promise"
                ),
            )
        elif not any(q["fy"] == fy for q in qs):
            v, why = "pending", f"Falls due with {period} results, not reported yet"
        else:
            # 1. what the company itself reported for this metric and year (its own definition)
            rep = reported_mod.best(reported or [], metric, fy, cc=True if cc_guided else None)
            if metric == "revenue_growth" and not cc_guided:
                rep = reported_mod.best(reported or [], metric, fy, cc=False)
            # 2. our own figure from the filings: the actual only where the filing is unambiguous
            comp = _computed(conn, cid, qs, metric, fy, fy_start, last)
            if cc_guided:
                if comp:
                    context = (
                        f"Reported ₹ growth {comp['value']}% ({comp['span']}), which includes currency moves"
                    )
                comp = None  # ₹ growth never stands in for constant-currency guidance
            if rep:
                act, cross = rep, comp
            elif comp and metric in COMPUTED_OK:
                act = comp
            if act is None:
                if comp and comp["quarters"] < 4:
                    v = "pending"
                    why = (
                        f"The company hasn't stated a year-to-date "
                        f"{METRIC_LABEL.get(metric, metric).lower()}; "
                        f"our estimate from the filings is {_fmt(comp)} (cross-check only)"
                    )
                else:
                    v = NOT_SCORED
                    why = "The company didn't state this figure in the calls read" + (
                        f"; our estimate from the filings is {_fmt(comp)} (cross-check only, not scored)"
                        if comp
                        else ", and it isn't in the results filings"
                    )
                    cross = comp
                act = None
            elif metric == "capex":
                v, why = _capex_verdict(act, last["high"])
            elif metric == "revenue" and last["unit"] == "₹ cr":
                a, lo, hi = act["value"], last["low"], last["high"]
                floor = is_floor(last)
                band = f"₹{lo:,.0f} cr" if lo == hi else f"₹{lo:,.0f}–{hi:,.0f} cr"
                v = "missed" if a < lo * 0.98 else "delivered" if floor or a <= hi * 1.02 else "beat"
                why = f"₹{a:,.0f} cr vs {band} guided"
            elif last["unit"] != "%":
                v, why = NOT_SCORED, "Guided in a unit the filings don't report"
                act = None
            else:
                v, why = verdict(
                    act,
                    last["low"],
                    last["high"],
                    act["quarters"] == 4,
                    lower,
                    is_floor(last),
                )
            # guided and actual far apart: probably a different scope or definition, unless the
            # quote itself names this exact fiscal year
            if act is not None and v in ("delivered", "beat", "missed") and _suspect(act, last, fy):
                gap = abs(act["value"] / ((last["low"] + last["high"]) / 2) - 1) * 100
                cross = act
                act = None
                v, why = (
                    NOT_SCORED,
                    (
                        f"Guided and actual differ by {gap:.0f}%, and the quote doesn't name {period}: "
                        "probably not the same measure, so not scored"
                    ),
                )
        first = pts[0]
        two = (first["low"], first["high"]) != (last["low"], last["high"])
        v_first, line, moved = None, None, None
        first_is_revision = bool(REVISED.search(first["quote"]))
        if act is not None and v in ("delivered", "beat", "missed"):
            v_first = _judge(act, first, metric, lower)[0] if two else v
            if v_first in VERB:
                line = _line(first, v_first, last, v, act, two)
            if first_is_revision:
                # we never saw the original: don't score against it, and say so
                v_first = None
                line = line or why
            mid1, mid2 = (first["low"] + first["high"]) / 2, (last["low"] + last["high"]) / 2
            moved = "lowered" if mid2 < mid1 - 1e-9 else "raised" if mid2 > mid1 + 1e-9 else None
        label = v
        if v in MET and moved == "lowered" and v_first not in MET:
            label = "met after cut"
        elif v == "missed" and moved == "lowered":
            label = "missed after cut"
        elif v == "beat" and moved == "raised":
            label = "beat raised"
        elif v in MET and first_is_revision:
            label = "met revised"
        if act and "source" not in act:
            act["source"] = {"xbrl": next((q["xbrl"] for q in reversed(qs) if q["fy"] == fy), None)}
        if cross and "source" not in cross:
            cross["source"] = {"xbrl": next((q["xbrl"] for q in reversed(qs) if q["fy"] == fy), None)}
        rr = (
            run_rate(qs, fy, metric, last)
            if v in ("on track", "ahead", "behind") and fy and not cc_guided
            else None  # a rupee run-rate means nothing next to a constant-currency band
        )
        cuts = sum(p["change"] == "cut" for p in pts)
        raises = sum(p["change"] == "raised" for p in pts)
        out.append(
            {
                "metric": metric,
                "label": METRIC_LABEL.get(metric, metric),
                "period": period,
                "points": pts,
                "actual": act,
                "cross_check": cross,
                "run_rate": rr,
                "context": context,
                "verdict": v,
                "verdict_label": label,
                "short": METRIC_SHORT.get(metric, METRIC_LABEL.get(metric, metric)),
                "verdict_first": v_first,
                "verdict_line": line,
                "moved": moved,
                "first_is_revision": first_is_revision,
                "steers": steer_map.get((metric, period), []),
                "verdict_why": why,
                "resolved": v in ("delivered", "missed", "beat"),
                "story": _story(METRIC_LABEL.get(metric, metric), period, pts, cuts, raises, v, act),
                "as_of_quarter": latest_q,
            }
        )
    order = {"revenue_growth": 0, "operating_margin": 1, "ebitda_margin": 1, "aum_growth": 2}
    return sorted(
        out,
        key=lambda t: (
            -(int(t["period"][2:]) if t["period"][2:].isdigit() else 0),
            order.get(t["metric"], 5),
        ),
    )


def _band(p: dict) -> str:
    u = p["unit"] or ""
    if p["low"] == p["high"]:
        return f"{p['low']:g}{u}" if u == "%" else f"{p['low']:g} {u}"
    return f"{p['low']:g}–{p['high']:g}{u}" if u == "%" else f"{p['low']:g}–{p['high']:g} {u}"


def _story(label: str, period: str, pts: list[dict], cuts: int, raises: int, v: str, act: dict | None) -> str:
    """The chain end to end: first given -> each revision -> outcome -> verdict."""
    seq = " → ".join(_band(p) for p in pts)
    s = f"{period} {label.lower()}: {seq}"
    if cuts:
        s += f" (cut {cuts}×)" if cuts > 1 else " (cut once)"
    elif raises:
        s += f" (raised {raises}×)" if raises > 1 else " (raised once)"
    elif len(pts) > 1:
        s += " (held)"
    if act:
        val = f"₹{act['value']:,.0f} cr" if act["unit"] == "₹ cr" else f"{act['value']}%"
        who = "company reported" if act.get("basis", "").startswith("company-reported") else "filings show"
        s += f" → {who} {val} ({act['span']})"
    return s + f" → {v}."


def signals(qs: list[dict], trks: list[dict], fmt: str) -> dict[str, list[str]]:
    """Bull and bear points computed from the numbers and the guidance record."""
    bull: list[str] = []
    bear: list[str] = []
    q = [x for x in qs if x["revenue"] is not None]
    if len(q) >= 5:
        last, yago = q[-1], q[-5]
        if last.get("revenue_yoy") is not None:
            (bull if last["revenue_yoy"] >= 10 else bear if last["revenue_yoy"] < 3 else bull).append(
                f"Revenue {last['revenue_yoy']:+.1f}% YoY in {last['label']}"
            )
        mk = "ebitda_margin" if fmt == "indas" else "pat_margin"
        if last.get(mk) is not None and yago.get(mk) is not None:
            d = round((last[mk] - yago[mk]) * 100)
            name = "EBITDA" if mk == "ebitda_margin" else "PAT"
            if abs(d) >= 50:
                (bull if d > 0 else bear).append(
                    f"{name} margin {last[mk]}% in {last['label']}, "
                    f"{'up' if d > 0 else 'down'} {abs(d)} bps YoY"
                )
        if last.get("pat_yoy") is not None and abs(last["pat_yoy"]) >= 5:
            (bull if last["pat_yoy"] > 0 else bear).append(
                f"PAT {last['pat_yoy']:+.1f}% YoY in {last['label']}"
            )
    for t in trks:
        if t["verdict"] in (NOT_SCORED, "open-ended"):
            continue  # bull/bear only from guidance we can hold the company to
        cuts = sum(p["change"] == "cut" for p in t["points"])
        raises = sum(p["change"] == "raised" for p in t["points"])
        chain = " → ".join(_band(p) for p in t["points"])
        name = f"{t['period']} {t['label'].lower()} guidance"
        if t["metric"] in LOWER_BETTER:  # a lower credit-cost guide is good news, a higher one bad
            if cuts:
                bull.append(f"{name} lowered {cuts}× ({chain})")
            if raises:
                bear.append(f"{name} raised {raises}× ({chain})")
        else:
            if cuts:
                bear.append(f"{name} cut {cuts}× ({chain})")
            if raises:
                bull.append(f"{name} raised {raises}×")
        if t["verdict"] in ("delivered", "beat"):
            bull.append(f"Delivered {t['period']} {t['label'].lower()}: {t['verdict_why']}")
        if t["verdict"] in ("missed", "behind"):
            bear.append(f"{t['period']} {t['label'].lower()} {t['verdict']}: {t['verdict_why']}")
    return {"bull": bull[:4], "bear": bear[:4]}


def group_chains(trks: list[dict]) -> list[dict]:
    """Chains stated together are shown together: same period and the same statements in the same
    order (one sentence carrying AUM growth, ROA and ROE) become one timeline whose steps show every
    number, each quote once. Per-metric verdicts stay separate."""
    keyed: dict[tuple, list[dict]] = {}
    for t in trks:
        if t["verdict"] == NOT_SCORED or not t["points"]:
            continue
        k = (t["period"], tuple((p["call_date"], p["quote"]) for p in t["points"]))
        keyed.setdefault(k, []).append(t)
    out = []
    for (period, _), ts in keyed.items():
        first = ts[0]["points"][0]
        name = f"{first.get('noun') or 'guidance'}" if len(ts) > 1 else ts[0]["label"]
        title = f"{period} {name}" if period.startswith("FY") else f"{name[0].upper()}{name[1:]} ({period})"
        steps = []
        for i, p in enumerate(ts[0]["points"]):
            steps.append(
                {
                    "kind": "statement",
                    "date": p["call_date"],
                    "call": p["call"],
                    "page": p.get("page"),
                    "url": p["url"],
                    "speaker": p.get("speaker"),
                    "quote": p["quote"],
                    "qualifier": next(
                        (t["points"][i].get("qualifier") for t in ts if t["points"][i].get("qualifier")), None
                    ),
                    "values": [
                        {
                            "metric": t["metric"],
                            "short": t.get("short"),
                            "low": t["points"][i]["low"],
                            "high": t["points"][i]["high"],
                            "unit": t["points"][i].get("unit"),
                            "floor": is_floor(t["points"][i]),
                            "change": "reiterated"
                            if t["points"][i].get("reiterates")
                            else t["points"][i]["change"],
                        }
                        for t in ts
                    ],
                }
            )
        seen = set()
        for t in ts:
            for st in t.get("steers") or []:
                key = (st["call_date"], st["reply_quote"])
                if key not in seen:
                    seen.add(key)
                    steps.append({"kind": "steer", "date": st["call_date"], **st})
        steps.sort(key=lambda x: x["date"])
        results: dict[str, dict] = {}
        for t in ts:
            a = t.get("actual")
            if not a:
                continue
            src = a.get("source") or {}
            key = src.get("quote") or src.get("xbrl") or t["metric"]
            r = results.setdefault(
                key, {"kind": "result", "source": src, "basis": a.get("basis"), "values": []}
            )
            r["values"].append(
                {
                    "metric": t["metric"],
                    "short": t.get("short"),
                    "value": a["value"],
                    "unit": a["unit"],
                    "span": a["span"],
                }
            )
        out.append(
            {
                "id": re.sub(r"[^a-z0-9]+", "-", f"{period}-{'-'.join(t['metric'] for t in ts)}".lower()),
                "period": period,
                "title": title,
                "resolved": any(t["resolved"] for t in ts),
                "metrics": [t["metric"] for t in ts],
                "steps": steps,
                "results": list(results.values()),
                "verdicts": [
                    {
                        "metric": t["metric"],
                        "short": t.get("short"),
                        "label": t.get("verdict_label") or t["verdict"],
                        "verdict": t["verdict"],
                        "line": t.get("verdict_line") or t["verdict_why"],
                        "caveat": t.get("caveat"),
                    }
                    for t in ts
                ],
                "cross_checks": [
                    {"short": t.get("short"), **t["cross_check"]} for t in ts if t.get("cross_check")
                ],
            }
        )
    rank = {"resolved": 0}
    out.sort(key=lambda g: (rank.get("resolved" if g["resolved"] else "", 1), _period_sort(g["period"])))
    return out


def _period_sort(period: str) -> int:
    return -int(period[2:]) if period[2:].isdigit() else 0


def ledger_questions(trks: list[dict], top: int = 3) -> list[str]:
    """What to ask, drawn only from this ledger's own numbers."""

    def band(p: dict) -> str:
        return _bandtxt(p)

    def val(a: dict | None) -> str:
        if not a:
            return "n/a"
        return f"₹{a['value']:,.0f} cr" if a.get("unit") == "₹ cr" else f"{a['value']:.1f}%"

    qs: list[tuple[int, str]] = []
    for t in trks:
        pts, a = t["points"], t.get("actual")
        if not pts:
            continue
        lbl = t["label"] if t["label"][:2].isupper() else t["label"][0].lower() + t["label"][1:]
        name = f"{t['period']} {lbl}"
        if t["resolved"] and t["verdict"] == "missed" and t.get("moved") == "lowered":
            qs.append(
                (
                    0,
                    f"{name} came in at {val(a)}, below guidance already lowered from {band(pts[0])} to "
                    f"{band(pts[-1])}. What drove the shortfall after the cut, and what is different now?",
                )
            )
        elif t["resolved"] and t.get("verdict_label") == "met after cut":
            qs.append(
                (
                    1,
                    f"{name} landed at {val(a)} against guidance lowered from {band(pts[0])} to "
                    f"{band(pts[-1])}. What forced the cut, and what would it take to reach the original?",
                )
            )
        elif t["resolved"] and t["verdict"] == "missed":
            qs.append((2, f"{name} came in at {val(a)} against {band(pts[-1])} guided. What was misjudged?"))
        elif not t["resolved"] and t.get("moved") == "raised" and a:
            qs.append(
                (
                    3,
                    f"{name} guidance was raised from {band(pts[0])} to {band(pts[-1])}, with "
                    f"{val(a)} so far. What would have to go wrong to miss it?",
                )
            )
    return [q for _, q in sorted(qs, key=lambda x: x[0])[:top]]


def build(conn: Connection, symbol: str, router: Router | None, nse: NSE | None, n_calls: int = 8) -> dict:
    row = conn.execute(
        "SELECT id, name, coalesce(fin_format, 'indas'), industry FROM companies WHERE nse_symbol = %s",
        (symbol,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown symbol {symbol}")
    cid, name, fmt, industry = row
    qs, fy_start = quarters(conn, cid, fmt)
    from finn.pull import business

    biz = business.snapshot(conn, cid, industry, fy_start)
    biz["about"] = business.about(conn, cid, router)
    biz["what"] = business.mix_line(biz)
    calls, stats, docs = [], [], []
    listed = tr.pick(conn, cid, n_calls)
    for d in tr.ensure_text(conn, nse, cid, n_calls):
        filed: datetime = d["filed_at"]
        # a call discusses the quarter just ended: it belongs to that quarter's fiscal year
        # default period for "this year": the fiscal year the call falls in (a Q4 call in April
        # guides the new year, which is also the year April falls in)
        items, st = gd.extract(router, d["pages"], _fy_of(filed.date(), fy_start))
        items = gd.annotate(items, d["pages"])
        call_steers = gd.steers(d["pages"])
        stats.append(st)
        qend = _quarter_before(filed.date())
        docs.append({**d, "qend": qend, "label": fiscal_label(qend, fy_start) + " call"})
        calls.append(
            {
                "label": fiscal_label(qend, fy_start) + " call",
                "filed_at": filed.isoformat(),
                "url": d["url"],
                "source": d.get("source") or "NSE",
                "pages": len(d["pages"]),
                "items": items,
                "steers": call_steers,
            }
        )
    said = reported_mod.outcomes(docs, fy_start, fiscal_label)
    trks = tracks(calls, qs, fy_start, conn, cid, said, lender=fmt in ("bank", "nbfc"))
    for t in trks:
        if t.get("first_is_revision") and t["resolved"]:
            t["caveat"] = f"Original guidance is in a call not read ({len(calls)} of {len(listed)})"
    resolved = [t for t in trks if t["resolved"]]
    return {
        "symbol": symbol,
        "name": name,
        "industry": industry,
        "format": fmt,
        "as_of": datetime.now().astimezone().isoformat(),
        "quarters": qs[-12:],
        "business": biz,
        "guidance": trks,
        "groups": group_chains(trks),
        "calls": [
            {k: v for k, v in c.items() if k not in ("items", "steers")} | {"n_items": len(c["items"])}
            for c in calls
        ],
        "signals": signals(qs, trks, fmt),
        "ledger": {
            "calls_listed": len(listed),
            "calls_read": len(calls),
            "resolved": len(resolved),
            "delivered": sum(t["verdict"] in ("delivered", "beat") for t in resolved),
            "missed": sum(t["verdict"] == "missed" for t in resolved),
            "open": sum(
                t["verdict"] in ("on track", "ahead", "behind", "pending", "open-ended") for t in trks
            ),
            "unverifiable": sum(t["verdict"] == NOT_SCORED for t in trks),
            "met_final": sum(t["verdict"] in MET for t in resolved),
            "met_first": sum(t.get("verdict_first") in MET for t in resolved),
            "first_known": sum(not t.get("first_is_revision") for t in resolved),
            "pattern": pattern(trks, len(calls), len(listed)),
        },
        "stats": stats,
        "sources": "Numbers: the company's quarterly XBRL results on NSE. Guidance: verbatim from its "
        "earnings-call transcripts (NSE, or the company's IR site where noted). No news, broker notes "
        "or model knowledge.",
    }


def _quarter_before(d: date) -> date:
    import calendar

    m = ((d.month - 1) // 3) * 3  # last month of the previous calendar quarter
    y = d.year if m else d.year - 1
    m = m or 12
    return date(y, m, calendar.monthrange(y, m)[1])


def materialise(
    conn: Connection, symbol: str, router: Router | None, nse: NSE | None, live: bool = False
) -> dict:
    body = build(conn, symbol, router, nse)
    # Reviewed = in the research set the owner and FINN checked by hand (data/research_set.json).
    # Anything else, and every on-demand run, says so on the page.
    reviewed = conn.execute(
        "SELECT 1 FROM research_set r JOIN companies c ON c.id = r.company_id WHERE c.nse_symbol = %s",
        (symbol,),
    ).fetchone()
    body["provenance"] = {"live": live, "reviewed": bool(reviewed) and not live}
    try:  # weave the network in: who to call about this company
        from finn.network.service import Net

        net = Net(conn)
        cands = net.who_for(symbol, top=6)
        company = body["name"]

        def tier(c: dict) -> int:  # former employees of this company, then peers, then current staff
            if c.get("compliance"):
                return 2
            return 0 if c.get("why", "").lower().startswith("worked at " + company.lower()) else 1

        cands.sort(key=lambda c: (tier(c), -c.get("rank", 0)))
        body["network"] = cands[:3]
        body["help"] = {
            "people": [],
            "call": cands[:5],
            "questions": ledger_questions(body["guidance"]),
            "points": 0,
        }
        note = net.last_note(symbol, [c["id"] for c in cands[:5]])
        if note:
            body["help"]["note"] = note  # the investor's own last meeting note on this company
    except Exception:
        conn.rollback()
        body["network"] = []
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES (%s, %s, now()) ON CONFLICT (key) DO UPDATE "
        "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
        (f"research:{symbol}", Jsonb(body)),
    )
    refresh_index(conn)
    return {"quarters": len(body["quarters"]), "guidance": len(body["guidance"]), "calls": len(body["calls"])}


def refresh_index(conn: Connection) -> None:
    """Rebuild `research:index` from the research views that exist."""
    roles: dict[str, str] = dict(
        conn.execute(
            "SELECT c.nse_symbol, r.role FROM research_set r JOIN companies c ON c.id = r.company_id"
        ).fetchall()
    )
    idx = [
        {
            "symbol": b["symbol"],
            "name": b["name"],
            "tracks": len(b["guidance"]),
            "calls": len(b["calls"]),
            "resolved": (b.get("ledger") or {}).get("resolved", 0),
            "role": roles.get(b["symbol"]),
            "hero": (roles.get(b["symbol"]) or "").lower().startswith("hero"),
        }
        for (b,) in conn.execute(
            "SELECT body FROM views WHERE key LIKE 'research:%%' AND key <> 'research:index' ORDER BY key"
        ).fetchall()
    ]
    idx.sort(key=lambda c: (not c["hero"], -c["resolved"], c["symbol"]))  # hero first, then by evidence
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES ('research:index', %s, now()) "
        "ON CONFLICT (key) DO UPDATE "
        "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
        (Jsonb({"companies": idx}),),
    )
    conn.commit()
