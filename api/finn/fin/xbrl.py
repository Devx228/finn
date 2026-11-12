"""Parse an exchange XBRL results instance into plain facts. No model; no interpretation.

Works for both NSE eras: `corporates-financial-results` XBRL (to Dec 2024) and SEBI Integrated
Filing XBRL (Mar 2025 on). Numeric facts are kept exactly as reported (monetary values in
absolute INR); text facts go to `meta`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
LINK = "{http://www.xbrl.org/2003/linkbase}"
XLINK = "{http://www.w3.org/1999/xlink}"


@dataclass(frozen=True)
class Fact:
    concept: str
    dims: str  # '' for plain facts; 'Axis=Member;...' for dimensioned (e.g. segments)
    period_start: date | None  # None for instants
    period_end: date
    value: Decimal
    unit: str | None


@dataclass
class ParsedXBRL:
    facts: list[Fact]
    meta: dict[str, str] = field(default_factory=dict)
    entry_point: str = ""

    @property
    def fmt(self) -> str:
        """'bank' | 'nbfc' | 'indas', from the taxonomy entry point the filer used."""
        ep = self.entry_point.lower()
        if "bank" in ep:
            return "bank"
        if "nbfc" in ep:
            return "nbfc"
        return "indas"

    def get(
        self, concept: str, period_end: date, period_start: date | None = None
    ) -> Decimal | None:
        for f in self.facts:
            if (
                f.concept == concept
                and not f.dims
                and f.period_end == period_end
                and (period_start is None or f.period_start == period_start)
            ):
                return f.value
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s.strip()[:10]) if s else None


def parse_xbrl(content: bytes) -> ParsedXBRL:
    root = ET.fromstring(content)

    entry = ""
    for ref in root.iter(f"{LINK}schemaRef"):
        entry = ref.get(f"{XLINK}href", "")

    contexts: dict[str, tuple[date | None, date, str]] = {}
    for ctx in root.iter(f"{XBRLI}context"):
        cid = ctx.get("id")
        period = ctx.find(f"{XBRLI}period")
        if cid is None or period is None:
            continue
        inst = _date(period.findtext(f"{XBRLI}instant"))
        start = _date(period.findtext(f"{XBRLI}startDate"))
        end = _date(period.findtext(f"{XBRLI}endDate"))
        dims = []
        for m in ctx.iter():
            if _local(m.tag) in ("explicitMember", "typedMember"):
                axis = _local(m.get("dimension", "").split(":")[-1])
                val = (m.text or "".join(c.text or "" for c in m)).strip()
                dims.append(f"{axis}={val.split(':')[-1]}")
        if inst is not None:
            contexts[cid] = (None, inst, ";".join(sorted(dims)))
        elif end is not None:
            contexts[cid] = (start, end, ";".join(sorted(dims)))

    units: dict[str, str] = {}
    for u in root.iter(f"{XBRLI}unit"):
        measures = [(m.text or "").split(":")[-1] for m in u.iter(f"{XBRLI}measure")]
        if u.get("id"):
            units[u.get("id", "")] = "/".join(measures)

    meta: dict[str, str] = {}
    raw: list[tuple[str, str, str, str | None]] = []  # concept, context id, text, unit id
    for el in root:
        ref = el.get("contextRef")
        if ref is None or ref not in contexts:
            continue
        name = _local(el.tag)
        text = (el.text or "").strip()
        if el.get("unitRef") is not None:
            if text and el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") != "true":
                raw.append((name, ref, text, el.get("unitRef")))
        elif text and not contexts[ref][2] and name not in meta:
            meta[name] = text[:2000]

    # NSE quirk (verified 2026-11-12): year-to-date contexts ("Four*") are declared with the
    # quarter's own dates while their values are year-to-date. Re-date them from the filing's
    # stated start of financial year so a quarter and a YTD figure never share one period key.
    fy_start = _date(meta.get("DateOfStartOfFinancialYear"))
    if fy_start:
        for cid, (start, end, dims) in list(contexts.items()):
            if cid.startswith("Four") and start is not None and start != fy_start:
                contexts[cid] = (fy_start, end, dims)

    facts: dict[tuple, Fact] = {}
    for name, ref, text, unit_id in raw:
        try:
            val = Decimal(text)
        except InvalidOperation:
            continue
        start, end, dims = contexts[ref]
        f = Fact(name, dims, start, end, val, units.get(unit_id or ""))
        facts.setdefault((name, dims, start, end), f)  # Q1: quarter == YTD; keep one
    return ParsedXBRL(facts=list(facts.values()), meta=meta, entry_point=entry)
