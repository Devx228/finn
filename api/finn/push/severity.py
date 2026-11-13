"""Stage 1b: read the text of event filings before scoring them (ranking fix, 2026-11-13).

An exchange category says what kind of filing it is, not how much it matters: "Action(s) taken
or orders passed" holds a ₹1 lakh telecom penalty and a pollution board shutting a plant; "order
win" holds ₹1,000 cr and ₹15,000 cr orders. So for event categories no rule keeps a flat score
without reading the text:

1. An operational stop (closure, suspension, licence cancelled, search, attachment) → top tier.
2. Otherwise the rupee amount at stake, as a share of the company's own trailing revenue. L&T-style
   order classes are converted using the band table printed in the same filing, never a table we
   supply. If the company itself states there is no material impact, that statement caps it.
3. Nothing a rule can judge → the hosted model rates it and writes the one-line fact.

Routine sub-types (results decks, monthly volumes, subsidiary incorporations, debt allotments)
keep their flat scores: they are paperwork whatever the text says.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EVENT = {"litigation", "press_release", "fund_raise", "M&A", "capex"}
ROUTINE_SUBTYPES = {"press_release", "business_update", "routine_subsidiary_infusion", "routine_debt"}
TOP_BASE = 72

OPSTOP = re.compile(
    r"clos(?:ure|e) of (?:the )?(?:manufacturing |production )?(?:operations|plant|unit|factory|facility)"
    r"|directing (?:the )?closure|shut[- ]?down of|\bsuspension of (?:operations|production|manufacturing|"
    r"(?:the )?licen[cs]e)|suspend(?:ed|ing)? (?:its |the )?(?:operations|production|manufacturing)"
    r"|licen[cs]e\w*.{0,40}\b(?:cancell?ed|revoked|suspended)|cancell?ation of (?:the |its )?licen[cs]e"
    r"|search (?:and|&) seizure|search operation|search proceedings|provisional(?:ly)? attach"
    r"|attachment of (?:the )?(?:property|properties|assets|bank accounts?)|debarr?ed|prohibited from",
    re.I,
)
NO_IMPACT = re.compile(
    r"no (?:major |material |significant |adverse )?impact on (?:the )?(?:financial|operations|business)"
    r"|not (?:have|expected to have) (?:any )?(?:material|significant) impact",
    re.I,
)
AMOUNT = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b\.?|lakhs?|lacs?|million|mn\b|billion|bn\b)?",
    re.I,
)
# What makes an amount "at stake", per kind of event. Amounts elsewhere in the text (cumulative
# sales, face values, past figures) are ignored; a generic press release has no stake words, so
# the model judges it.
STAKE_WORDS = {
    "litigation": r"penalt|demand|fine\b|disincentive|liabilit|impact|claim|damages|compensation",
    "order_win": r"\border|contract|worth|valued|value of",
    "fund_raise": r"aggregat|raise|issue size|gross proceeds|amount of|size of the issue",
    "M&A": r"consideration|purchase price|deal value|enterprise value|acquisition cost|invest|valuation",
    "capex": r"invest|outlay|capex|capital expenditure|project cost|estimated cost",
}
PER_UNIT = re.compile(
    r"\beach\b|per (?:equity )?share|face value|issue price|floor price|premium|per unit", re.I
)
DEBT = re.compile(r"\b(commercial paper|non[- ]convertible|ncds?\b|debentures?|bonds?\b)", re.I)
EQUITY = re.compile(r"\b(qualified institutional|qip\b|preferential|rights issue|buy-?back|warrants)", re.I)
UNIT_TO_CR = {
    "crore": 1.0,
    "cr": 1.0,
    "lakh": 0.01,
    "lac": 0.01,
    "million": 0.1,
    "mn": 0.1,
    "billion": 100.0,
    "bn": 100.0,
}
CLASS = re.compile(r"\(\s*\*?\s*(significant|large|major|mega|ultra[- ]mega)\s*\*?\s*\)", re.I)


@dataclass
class Severity:
    base: int
    reason: str
    needs_model: bool = False
    amount_cr: float | None = None


def _to_cr(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    if not unit:
        return v / 1e7  # plain rupees
    u = unit.lower().rstrip(".").rstrip("s")
    return v * UNIT_TO_CR.get(u, 1.0)


def stake_amount(text: str, kind: str) -> float | None:
    """The largest rupee amount stated next to a word that says it is at stake for this kind of
    event (a penalty, an order's value, the amount raised...). Per-share figures are skipped."""
    words = STAKE_WORDS.get(kind)
    if words is None:
        return None
    rx = re.compile(words, re.I)
    best = None
    for m in AMOUNT.finditer(text):
        ctx = text[max(0, m.start() - 140) : m.end() + 60]
        if not rx.search(ctx) or PER_UNIT.search(text[max(0, m.start() - 30) : m.end() + 40]):
            continue
        try:
            v = _to_cr(m.group(1), m.group(2))
        except ValueError:
            continue
        if v > 0 and (best is None or v > best):
            best = v
    return best


def band_from_filing(text: str, subject: str) -> float | None:
    """'L&T bags (Significant*) order' + the filing's own table 'Significant Large ... Value in ₹ Cr
    1,000 to 2,500 2,500 to 5,000 ...' → the lower bound of that class (₹ cr)."""
    m = CLASS.search(f"{subject} {text[:3000]}")
    if not m:
        return None
    t = re.sub(r"\s+", " ", text)
    tab = re.search(r"Classification\s+((?:[A-Za-z-]+\s+){2,7}?)Value in ₹ ?Cr\s+(.{0,160})", t)
    if not tab:
        return None
    labels = [w.lower() for w in tab.group(1).split() if w.lower() != "classification"]
    ranges = re.findall(r"([\d,]+)\s*(?:to|-|–)\s*[\d,]+|>\s*([\d,]+)", tab.group(2))
    lows = [float((a or b).replace(",", "")) for a, b in ranges]
    want = m.group(1).lower().replace(" ", "-")
    if len(lows) < len(labels) or want not in labels:
        return None
    return lows[labels.index(want)]


def ratio_base(amount_cr: float, revenue_cr: float) -> int:
    r = amount_cr / revenue_cr
    return (
        65
        if r >= 0.10
        else 55
        if r >= 0.03
        else 46
        if r >= 0.01
        else 36
        if r >= 0.0025
        else 24
        if r >= 0.0005
        else 12
    )


def assess(
    category: str,
    sub_type: str | None,
    base: int,
    reason: str,
    subject: str,
    text: str | None,
    revenue_cr: float | None,
) -> Severity | None:
    """None: not an event filing (or routine) — keep the rule's score."""
    if category not in EVENT or (sub_type in ROUTINE_SUBTYPES):
        return None
    if not text:
        return Severity(base, f"{reason}; filing text not read yet", needs_model=True)
    t = re.sub(r"\s+", " ", text)
    if category == "fund_raise" and DEBT.search(t[:3000]) and not EQUITY.search(t[:3000]):
        return Severity(min(base, 12), "debt raised or allotted (routine treasury)")
    if OPSTOP.search(t):
        m = OPSTOP.search(t)
        return Severity(
            TOP_BASE, f"operational stop stated in the filing: “{m.group(0)}”" if m else "operational stop"
        )
    kind = "order_win" if sub_type == "order_win" else category
    amount = band_from_filing(t, subject) if kind == "order_win" else None
    how = (
        "order class from the filing's own table (lower bound)"
        if amount
        else "amount at stake stated in the filing"
    )
    if amount is None:
        amount = stake_amount(t, kind)
    if amount is None or not revenue_cr:
        return Severity(base, reason, needs_model=True)
    b = ratio_base(amount, revenue_cr)
    why = f"₹{amount:,.2f} cr = {amount / revenue_cr * 100:.2f}% of trailing revenue ({how})"
    if NO_IMPACT.search(t):
        b = min(b, 38)
        why += "; the company states no material impact"
    return Severity(b, why, amount_cr=amount)


# -- one-line facts ------------------------------------------------------------------------------
EMPTY = re.compile(
    r"press release (?:dated|on|titled)|informed the exchange|has issued a press release|"
    r"regarding (?:a|the) press release|outcome of .{0,40}meeting|corporate dossier|"
    r"^(?:press release|general updates?|updates?|action\(s\) taken or orders passed)\b",
    re.I,
)
DATEISH = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)? )?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w* "
    r"\d{1,2},? \d{4}\b|\b\d{4}\b",
    re.I,
)


def says_nothing(line: str | None, exch_category: str | None = None) -> bool:
    """True for a 'summary' that tells the reader nothing: the exchange's generic label, 'Press
    release on 20 October 2026', 'X informed the Exchange regarding ...'."""
    s = (line or "").strip()
    if not s:
        return True
    if EMPTY.search(s):
        return True
    if exch_category and s.strip(" .").lower() == exch_category.strip().lower():
        return True
    content = [
        w
        for w in re.findall(r"[A-Za-z]{3,}", DATEISH.sub(" ", s))
        if w.lower()
        not in {
            "the",
            "and",
            "for",
            "with",
            "company",
            "limited",
            "press",
            "release",
            "dated",
            "titled",
            "regarding",
        }
    ]
    return len(content) < 3


def verbatim_fact(text: str, pattern: re.Pattern[str], words: int = 28) -> str | None:
    """The sentence of the filing that carries the matched fact, verbatim, clipped to `words`."""
    t = re.sub(r"\s+", " ", text)
    m = pattern.search(t)
    if not m:
        return None
    a = max(t.rfind(". ", 0, m.start()) + 2, 0)
    b = t.find(". ", m.end())
    sent = t[a : b + 1 if b > 0 else len(t)].strip()
    ws = sent.split()
    return sent if len(ws) <= words else " ".join(ws[:words]).rstrip(",;:") + "…"


TOKEN = re.compile(
    r"\b(?:Q[1-4]|H[12]|FY\s?'?\d{2}(?:-\d{2})?)\b|\d[\d,]*(?:\.\d+)?",
    re.I,
)


def grounded(line: str, text: str) -> bool:
    """Every period label (Q2, H1, FY27) and number in a model-written line must appear in the
    filing's own text; otherwise the line may be wrong ('Q3' for a Q2 filing) and is not used."""
    t = re.sub(r"[\s,]+", " ", text or "").lower()
    t_nocomma = t.replace(",", "")
    for m in TOKEN.finditer(line):
        tok = m.group(0).lower().replace(" ", "").replace("'", "")
        if tok.isdigit() and len(tok) <= 2 and int(tok) <= 31:
            continue  # small numbers (days, counts) are too common to check meaningfully
        plain = tok.replace(",", "")
        if tok.startswith(("q", "h")):
            if not re.search(rf"\b{tok}\b|\b{'quarter' if tok[0] == 'q' else 'half'}", t):
                return False
            if tok[0] == "q" and not re.search(rf"\b{tok}\b", t):
                # 'Q2' may be written as 'second quarter' / 'quarter ended September'
                ordinal = {"q1": "first", "q2": "second", "q3": "third", "q4": "fourth"}[tok]
                if ordinal not in t:
                    return False
        elif tok.startswith("fy"):
            yy = re.sub(r"\D", "", tok)[:2]
            if not re.search(rf"fy\s?'?{yy}|20{yy}|{int(yy) - 1:02d}-{yy}", t):
                return False
        elif plain not in t_nocomma.replace(" ", " "):
            return False
    return True
