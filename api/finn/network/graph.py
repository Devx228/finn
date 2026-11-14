"""Network scoring (spec §9.2–9.6). Deterministic and explainable: every number comes with the
evidence sentence that produced it. No model is involved in ranking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

TODAY = date(2026, 11, 13)
LABELS = ((0.66, "strong"), (0.33, "medium"), (0.0, "weak"))
EVENT_FUNCTIONS = {
    "management_change": {"general-management", "finance", "HR"},
    "capex": {"operations", "finance", "R&D-technical"},
    "litigation": {"legal-compliance"},
    "M&A": {"strategy", "finance", "general-management"},
    "results": {"finance", "IR"},
    "fund_raise": {"finance", "treasury-credit"},
}


def label(x: float) -> str:
    return next(name for cut, name in LABELS if x >= cut)


@dataclass
class Emp:
    org_id: int
    org: str
    title: str | None
    function: str | None
    seniority: int | None
    start: date | None
    end: date | None  # None = current
    # a filing bio gave a start but no end and no later employer: when they left is unknown, so the
    # span is shown "from <year>" and never used as evidence of overlap
    open_unknown: bool = False


@dataclass
class Edu:
    org_id: int
    org: str
    degree: str | None
    end_y: int | None


@dataclass
class Person:
    id: int
    name: str
    kind: str
    is_synthetic: bool
    emps: list[Emp] = field(default_factory=list)
    edus: list[Edu] = field(default_factory=list)
    # relationship to the investor (contacts only)
    how_known: str | None = None
    since: date | None = None
    last_contact: date | None = None
    interactions_24m: int = 0
    closeness: int = 0


def _months(a: date, b: date) -> float:
    return (b.year - a.year) * 12 + (b.month - a.month)


def warmth(p: Person, today: date = TODAY) -> tuple[float, str]:
    """Investor ↔ contact, 0–1 (spec §9.2)."""
    if p.last_contact is None:
        return 0.0, "no relationship recorded"
    since_m = max(0.0, _months(p.last_contact, today))
    recency = 0.5 ** (since_m / 9)
    tenure = min(10.0, _months(p.since, today) / 12) / 10 if p.since else 0.0
    w = 0.35 * (p.closeness / 5) + 0.30 * recency + 0.20 * min(p.interactions_24m, 8) / 8 + 0.15 * tenure
    last = p.last_contact.strftime("%b %Y")
    return round(w, 2), f"{p.how_known}, last spoke {last}, {p.interactions_24m} interactions in 24 months"


def _size_discount(org_large: bool) -> float:
    return 0.6 if org_large else 1.0


def overlap(a: Person, b: Person, large_orgs: set[int] | None = None) -> tuple[float, list[str]]:
    """Person ↔ person, 0–1, from shared history. Max over evidence; all evidence kept."""
    large_orgs = large_orgs or set()
    best, ev = 0.0, []
    for x in a.emps:
        for y in b.emps:
            if x.org_id != y.org_id or not x.start or not y.start or x.open_unknown or y.open_unknown:
                continue
            start = max(x.start, y.start)
            end = min(x.end or TODAY, y.end or TODAY)
            m = _months(start, end)
            if m <= 0:
                continue
            same_fn = bool(x.function and x.function == y.function)
            prox = 1.0 - 0.15 * abs((x.seniority or 3) - (y.seniority or 3))
            s = (
                min(m, 48)
                / 48
                * (1.0 if same_fn else 0.6)
                * max(0.4, prox)
                * _size_discount(x.org_id in large_orgs)
            )
            ev.append(
                f"overlapped at {x.org}, {start.year}–{end.year if end < TODAY else 'now'}"
                + (f", both in {x.function}" if same_fn else "")
            )
            best = max(best, s)
    for u in a.edus:
        for v in b.edus:
            if u.org_id != v.org_id:
                continue
            cohort = u.end_y and v.end_y and abs(u.end_y - v.end_y) <= 2
            s = 0.5 if (cohort and u.degree and u.degree == v.degree) else 0.25
            ev.append(f"both studied at {u.org}" + (f" ({u.degree}, around {u.end_y})" if cohort else ""))
            best = max(best, s)
    return round(best, 2), ev


@dataclass
class Path:
    contact: Person
    target: Person
    warmth: float
    overlap: float
    score: float
    sentence: str


def paths(
    target: Person, contacts: list[Person], large_orgs: set[int] | None = None, top: int = 5
) -> list[Path]:
    """Second-degree reach (spec §9.3): You → contact → target."""
    out = []
    for c in contacts:
        o, ev = overlap(c, target, large_orgs)
        if o <= 0:
            continue
        w, wev = warmth(c)
        s = round(w * o, 3)
        out.append(
            Path(
                c,
                target,
                w,
                o,
                s,
                f"You → {c.name} ({wev}) → {target.name}: {ev[0]}. Path: {label(w)} × {label(o)}.",
            )
        )
    return sorted(out, key=lambda p: -p.score)[:top]


@dataclass
class Candidate:
    person: Person
    relevance: float
    warmth: float
    rank: float
    why: str
    what_theyd_know: str
    compliance: str | None


def who(
    company_org: int,
    peers: set[int],
    industry_orgs: set[int],
    contacts: list[Person],
    event: str | None = None,
    company_name: str = "the company",
    top: int = 5,
) -> list[Candidate]:
    """Who should I call (spec §9.4). Former employees and adjacent-company contacts rank above
    current employees (compliance guardrail §9.6)."""
    fns = EVENT_FUNCTIONS.get(event or "", set())
    out = []
    for c in contacts:
        best, why, know, current_here = 0.0, "", "", False
        for e in c.emps:
            if e.org_id == company_org:
                fit, rel = 1.0, f"worked at {company_name}"
            elif e.org_id in peers:
                fit, rel = 0.7, f"worked at peer {e.org}"
            elif e.org_id in industry_orgs:
                fit, rel = 0.4, f"worked in the same industry ({e.org})"
            else:
                continue
            years_since = 0.0 if e.end is None else max(0.0, _months(e.end, TODAY) / 12)
            recency = 1.0 if e.end is None else 0.5 ** (years_since / 4)
            fn_fit = 1.0 if (not fns or (e.function in fns)) else 0.6
            senior = 0.6 + 0.1 * (e.seniority or 3)
            r = fit * recency * fn_fit * senior
            if e.org_id == company_org and e.end is None:
                current_here = True
                r *= 0.7  # prefer former employees for company-specific questions
            if r > best:
                span = f"{e.start.year if e.start else '?'}–{e.end.year if e.end else 'now'}"
                best = r
                why = f"{rel} as {e.title or e.function} ({span})"
                know = f"How {e.org} runs {e.function or 'the business'}" + (
                    " today" if e.end is None else f" up to {e.end.year}"
                )
        if best <= 0:
            continue
        w, wev = warmth(c)
        rank = (best**0.6) * (max(w, 0.01) ** 0.4)
        flag = (
            f"Current employee of {company_name} — treat as a potential insider. Don't seek "
            "unpublished price-sensitive information; keep to public and industry context."
            if current_here
            else None
        )
        out.append(Candidate(c, round(best, 2), w, round(rank, 3), f"{why}; {wev}", know, flag))
    # A current employee can still be useful for public industry context, but should never be
    # the first suggested call. Keep the relevance order within the former/current groups.
    return sorted(out, key=lambda x: (x.compliance is not None, -x.rank))[:top]


def recency_decay(months: float, half_life: float) -> float:
    return math.pow(0.5, months / half_life)
