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


def verdict(
    actual: dict | None, low: float, high: float, final: bool, lower_better: bool = False
) -> tuple[str, str]:
    if actual is None:
        return NOT_SCORED, "No actual for this period"
    v = actual["value"]
    slack = 0.05  # rounding only: reported figures carry one decimal
    band = f"{low:g}–{high:g}%" if low != high else f"{low:g}%"
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
            v, why = "open-ended", "No year attached, so it never falls due; listed, not scored"
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
                hit = act["value"] >= last["low"] * 0.98
                v = "delivered" if hit else "missed"
                why = f"₹{act['value']:,.0f} cr vs ₹{last['low']:,.0f} cr guided"
            elif last["unit"] != "%":
                v, why = NOT_SCORED, "Guided in a unit the filings don't report"
                act = None
            else:
                v, why = verdict(act, last["low"], last["high"], act["quarters"] == 4, lower)
        if act and "source" not in act:
            act["source"] = {"xbrl": next((q["xbrl"] for q in reversed(qs) if q["fy"] == fy), None)}
        if cross and "source" not in cross:
            cross["source"] = {"xbrl": next((q["xbrl"] for q in reversed(qs) if q["fy"] == fy), None)}
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
                "context": context,
                "verdict": v,
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


def build(conn: Connection, symbol: str, router: Router | None, nse: NSE | None, n_calls: int = 8) -> dict:
    row = conn.execute(
        "SELECT id, name, coalesce(fin_format, 'indas'), industry FROM companies WHERE nse_symbol = %s",
        (symbol,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown symbol {symbol}")
    cid, name, fmt, industry = row
    qs, fy_start = quarters(conn, cid, fmt)
    calls, stats, docs = [], [], []
    listed = tr.pick(conn, cid, n_calls)
    for d in tr.ensure_text(conn, nse, cid, n_calls):
        filed: datetime = d["filed_at"]
        # a call discusses the quarter just ended: it belongs to that quarter's fiscal year
        # default period for "this year": the fiscal year the call falls in (a Q4 call in April
        # guides the new year, which is also the year April falls in)
        items, st = gd.extract(router, d["pages"], _fy_of(filed.date(), fy_start))
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
            }
        )
    said = reported_mod.outcomes(docs, fy_start, fiscal_label)
    trks = tracks(calls, qs, fy_start, conn, cid, said, lender=fmt in ("bank", "nbfc"))
    resolved = [t for t in trks if t["resolved"]]
    return {
        "symbol": symbol,
        "name": name,
        "industry": industry,
        "format": fmt,
        "as_of": datetime.now().astimezone().isoformat(),
        "quarters": qs[-12:],
        "guidance": trks,
        "calls": [{k: v for k, v in c.items() if k != "items"} | {"n_items": len(c["items"])} for c in calls],
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


def materialise(conn: Connection, symbol: str, router: Router | None, nse: NSE | None) -> dict:
    body = build(conn, symbol, router, nse)
    try:  # weave the network in: who to call about this company
        from finn.network.service import Net

        body["network"] = Net(conn).who_for(symbol, top=3)
    except Exception:
        conn.rollback()
        body["network"] = []
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES (%s, %s, now()) ON CONFLICT (key) DO UPDATE "
        "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
        (f"research:{symbol}", Jsonb(body)),
    )
    roles = dict(
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
    return {"quarters": len(body["quarters"]), "guidance": len(body["guidance"]), "calls": len(body["calls"])}
