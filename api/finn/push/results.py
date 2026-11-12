"""Results card (spec §8.3) computed from exchange XBRL facts. No model touches a number.

Metric sets by format:
- indas (operating companies): Revenue, EBITDA, PBT, PAT.
  EBITDA = profit before exceptional items and tax + finance costs + depreciation & amortisation
  − other income (the reference's definition, excluding other income so it measures the core
  business; Indian results statements do not print EBITDA).
- bank: Net interest income (interest earned − interest expended), pre-provision operating
  profit, PBT, PAT. EBITDA is meaningless for a bank and is not shown.
- nbfc: Revenue, net interest income (interest earned − finance costs), PBT, PAT.

Validation: the filing's own identities must hold (indas/nbfc: Income − Expenses = profit before
exceptional items and tax; bank: Income − expenditure − provisions + exceptional = PBT), within
0.5% (rounding). QoQ / YoY are computed only against the same basis; a basis switch is labelled,
never spliced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

CR = Decimal(10**7)
TOL = Decimal("0.005")
ONE_LINE_WORDS = 20

# (metric key, label, how to compute from a {concept: value} dict)
FACT = dict[str, Decimal]


def _g(f: FACT, *names: str) -> Decimal | None:
    for n in names:
        if n in f:
            return f[n]
    return None


def _pbe(f: FACT) -> Decimal | None:
    v = _g(f, "ProfitBeforeExceptionalItemsAndTax")
    if v is not None:
        return v
    pbt, exc = _g(f, "ProfitBeforeTax"), _g(f, "ExceptionalItemsBeforeTax", "ExceptionalItems")
    return None if pbt is None else pbt - (exc or Decimal(0))


def metrics(fmt: str, f: FACT) -> dict[str, Decimal | None]:
    if fmt == "bank":
        ie, ix = _g(f, "InterestEarned"), _g(f, "InterestExpended")
        return {
            "nii": None if ie is None or ix is None else ie - ix,
            "ppop": _g(f, "OperatingProfitBeforeProvisionAndContingencies"),
            "pbt": _g(f, "ProfitLossFromOrdinaryActivitiesBeforeTax", "ProfitBeforeTax"),
            "pat": _g(f, "ProfitLossForThePeriod", "ProfitLossForPeriod"),
            "total_income": _g(f, "Income"),
        }
    rev = _g(f, "RevenueFromOperations")
    pat = _g(f, "ProfitLossForPeriod", "ProfitLossForThePeriod")
    pbt = _g(f, "ProfitBeforeTax")
    if fmt == "nbfc":
        ie, fc = _g(f, "InterestEarned"), _g(f, "FinanceCosts")
        return {"revenue": rev, "nii": None if ie is None or fc is None else ie - fc, "pbt": pbt, "pat": pat}
    pbe, fc, da, oi = (
        _pbe(f),
        _g(f, "FinanceCosts"),
        _g(f, "DepreciationDepletionAndAmortisationExpense"),
        _g(f, "OtherIncome"),
    )
    ebitda = None if None in (pbe, fc, da, oi) else pbe + fc + da - oi  # type: ignore[operator]
    return {"revenue": rev, "ebitda": ebitda, "pbt": pbt, "pat": pat}


LABELS = {
    "revenue": "Revenue",
    "ebitda": "EBITDA",
    "pbt": "PBT",
    "pat": "PAT",
    "nii": "Net interest income",
    "ppop": "Pre-provision op. profit",
    "total_income": "Total income",
}
ROWS = {
    "indas": ["revenue", "ebitda", "pbt", "pat"],
    "nbfc": ["revenue", "nii", "pbt", "pat"],
    "bank": ["nii", "ppop", "pbt", "pat"],
}


def validate(fmt: str, f: FACT) -> list[str]:
    issues = []

    def close(a: Decimal, b: Decimal) -> bool:
        return abs(a - b) <= TOL * max(abs(a), abs(b), Decimal(1))

    if fmt == "bank":
        inc, exp_, prov = (
            _g(f, "Income"),
            _g(f, "ExpenditureExcludingProvisionsAndContingencies"),
            _g(f, "ProvisionsOtherThanTaxAndContingencies"),
        )
        exc = _g(f, "ExceptionalItems") or Decimal(0)
        pbt = _g(f, "ProfitLossFromOrdinaryActivitiesBeforeTax")
        if None in (inc, exp_, prov, pbt):
            issues.append("bank identity not checkable (lines missing)")
        elif not close(inc - exp_ - prov + exc, pbt):  # type: ignore[operator,arg-type]
            issues.append("income − expenditure − provisions ≠ PBT")
    else:
        inc, exp_, pbe = _g(f, "Income"), _g(f, "Expenses"), _pbe(f)
        if None in (inc, exp_, pbe):
            issues.append("P&L identity not checkable (lines missing)")
        else:
            assoc = _g(
                f, "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod"
            ) or Decimal(0)
            if not (close(inc - exp_, pbe) or close(inc - exp_ + assoc, pbe)):  # type: ignore[operator,arg-type]
                issues.append("income − expenses ≠ profit before exceptional items and tax")
        rev, oi = _g(f, "RevenueFromOperations"), _g(f, "OtherIncome")
        if inc is not None and rev is not None and oi is not None and not close(rev + oi, inc):
            issues.append("revenue + other income ≠ total income")
    m = metrics(fmt, f)
    for k in ROWS[fmt]:
        if m.get(k) is None:
            issues.append(f"{LABELS[k]} not reported")
    return issues


def pct(a: Decimal | None, b: Decimal | None) -> float | None:
    """% change; None when either side is missing or the base is zero/negative (a % change
    against a loss is misleading — the card shows the values instead)."""
    if a is None or b is None or b <= 0:
        return None
    return round(float((a - b) / abs(b) * 100), 1)


@dataclass
class Period:
    end: date
    basis: str
    facts: FACT
    xbrl_url: str
    audited: bool | None = None


@dataclass
class Card:
    rows: list[dict]
    margins: dict
    verified: bool
    issues: list[str]
    take: str
    basis_note: str | None = None
    extra: dict = field(default_factory=dict)


def _bps(a: Decimal | None, ra: Decimal | None, b: Decimal | None, rb: Decimal | None) -> tuple:
    if None in (a, ra, b, rb) or ra == 0 or rb == 0:
        return None, None
    m1 = float(a / ra * 100)  # type: ignore[operator]
    m0 = float(b / rb * 100)  # type: ignore[operator]
    return round(m1, 1), round((m1 - m0) * 100)


def build(fmt: str, cur: Period, prev_q: Period | None, prev_y: Period | None) -> Card:
    m = metrics(fmt, cur.facts)
    issues = validate(fmt, cur.facts)
    notes = []
    q = prev_q if prev_q and prev_q.basis == cur.basis else None
    y = prev_y if prev_y and prev_y.basis == cur.basis else None
    if prev_q and not q:
        notes.append(f"QoQ omitted: previous quarter is {prev_q.basis}")
    if prev_y and not y:
        notes.append(f"YoY omitted: year-ago quarter is {prev_y.basis}")
    mq = metrics(fmt, q.facts) if q else {}
    my = metrics(fmt, y.facts) if y else {}
    rows = []
    for k in ROWS[fmt]:
        v = m.get(k)
        rows.append(
            {
                "metric": k,
                "label": LABELS[k],
                "value_cr": None if v is None else round(float(v / CR), 1),
                "qoq_pct": pct(v, mq.get(k)),
                "yoy_pct": pct(v, my.get(k)),
            }
        )
    margins = {}
    denom = "revenue" if fmt != "bank" else "total_income"
    for k in ("ebitda", "pat"):
        if k in m:
            now_m, d_yoy = _bps(m.get(k), m.get(denom), my.get(k), my.get(denom))
            margins[f"{k}_margin_pct"], margins[f"{k}_margin_bps_yoy"] = now_m, d_yoy
    return Card(
        rows=rows,
        margins=margins,
        verified=not issues,
        issues=issues,
        take=one_line(fmt, rows, margins),
        basis_note="; ".join(notes) or None,
    )


def _sign(x: float) -> str:
    return f"+{x:.0f}%" if x >= 0.5 else (f"{x:.0f}%" if x <= -0.5 else "flat")


def one_line(fmt: str, rows: list[dict], margins: dict) -> str:
    """Generated from computed numbers only; ≤ 20 words."""
    r = {x["metric"]: x for x in rows}
    lead = "revenue" if fmt != "bank" else "nii"
    parts = []
    if r.get(lead, {}).get("yoy_pct") is not None:
        parts.append(f"{r[lead]['label']} {_sign(r[lead]['yoy_pct'])} YoY")
    bps = margins.get("ebitda_margin_bps_yoy")
    if bps is not None and abs(bps) >= 50:
        parts.append(f"EBITDA margin {'up' if bps > 0 else 'down'} {abs(bps)} bps")
    if r.get("pat", {}).get("yoy_pct") is not None:
        parts.append(f"PAT {_sign(r['pat']['yoy_pct'])}")
    text = "; ".join(parts) + "." if parts else "No year-ago quarter to compare."
    words = text.split()
    return text if len(words) <= ONE_LINE_WORDS else " ".join(words[:ONE_LINE_WORDS]) + "…"


def fiscal_label(end: date, fy_start_month: int) -> str:
    q = ((end.month - fy_start_month) % 12) // 3 + 1
    if fy_start_month == 1:
        return f"Q{q} CY{end.year % 100:02d}"
    fy = end.year + (1 if end.month >= fy_start_month else 0)
    return f"Q{q} FY{fy % 100:02d}"
