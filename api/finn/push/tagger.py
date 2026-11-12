"""Minimal headline tagger (Phase 1, for pick_portfolio.py only).

Maps an NSE announcement to one of the reference categories using the exchange category and
subject text. The full two-stage classifier (spec §8.1) replaces this in Phase 2.
"""

from __future__ import annotations

import re

from finn.sources.base import Announcement

KMP_ROLE = re.compile(
    r"\b(chief executive|ceo|chief financial|cfo|managing director|\bmd\b|whole[- ]?time director"
    r"|key managerial|kmp|chairman|chairperson)\b",
    re.I,
)
CHANGE = re.compile(r"\b(appoint|resign|cessation|re-?designat|retire|step(ped|s)? down|demise)", re.I)
MNA = re.compile(
    r"\b(acqui(re|sition)|merger|amalgamat|demerger|scheme of arrangement|joint venture"
    r"|stake sale|divest|disinvest)",
    re.I,
)
CAPEX = re.compile(
    r"\b(capex|capital expenditure|capacity expansion|new (plant|facility|unit)|greenfield"
    r"|brownfield|commission(ed|ing) of)",
    re.I,
)
LITIGATION = re.compile(
    r"\b(litigation|penalty|show cause|demand order|tax demand|nclt|insolvency|court"
    r"|tribunal|sebi order|regulatory action)\b",
    re.I,
)
RESULTS = re.compile(r"financial results?", re.I)


def tag(a: Announcement) -> str:
    cat = (a.category or "").lower()
    text = f"{a.category or ''} {a.subject or ''}"
    if "financial result" in cat or ("outcome of board meeting" in cat and RESULTS.search(text)):
        return "results"
    if (
        "change in director" in cat
        or "key managerial" in cat
        or "change in management" in cat
        or "resignation" in cat
        or "appointment" in cat
    ) or (CHANGE.search(text) and KMP_ROLE.search(text)):
        return "management_change"
    if "acquisition" in cat or "amalgamation" in cat or "restructuring" in cat or MNA.search(text):
        return "M&A"
    if "litigation" in cat or "action(s)" in cat or LITIGATION.search(text):
        return "litigation"
    if CAPEX.search(text):
        return "capex"
    return "other"


def is_kmp_change(a: Announcement) -> bool:
    """CEO / CFO / MD-level change (not independent-director rotation)."""
    text = f"{a.category or ''} {a.subject or ''}"
    return tag(a) == "management_change" and bool(KMP_ROLE.search(text)) and bool(CHANGE.search(text))
