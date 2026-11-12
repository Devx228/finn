"""Stage 2 classifier: batched BULK model for filings the rules cannot place (spec §8.1).

Input per filing: exchange category, subject, and — only when the subject is boilerplate — the
first ~1,500 characters of the PDF text. Ten filings per call. Output is validated against a
schema; the one-line summary's word budget is enforced in code, not trusted to the model.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from finn.push.classify_rules import CATEGORIES, Classified

PROMPT_VERSION = "classify_batch-v3"
BATCH = 5
ONE_LINE_WORDS = 18
TEXT_CHARS = 1500

Category = Literal[
    "results",
    "M&A",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
]
assert set(Category.__args__) == set(CATEGORIES)  # type: ignore[attr-defined]

THIN = re.compile(
    r"^\s*(\S.{0,80})?(informed the exchange (about|regarding) (general )?updates?\.?|"
    r"(intimation|disclosure) under regulation 30|titled \"press release\"|"
    r"regarding an update|outcome of board meeting held|'updates'|general updates)",
    re.I,
)


WS = re.compile(r"\s+")
# Where the content of an exchange letter starts (after letterhead and exchange addresses).
SALIENT = re.compile(r"\b(Sub(ject)?\s*[:.\-]|Re\s*:|Ref\s*:|Dear (Sir|Madam|Ma.am)[^,]{0,20},)", re.I)


def salient(text: str | None) -> str:
    """The part of a filing letter that says what it is about: from the subject line on."""
    t = WS.sub(" ", text or "")
    m = SALIENT.search(t)
    return t[m.start() :] if m else t


def thin_subject(subject: str | None) -> bool:
    s = (subject or "").strip()
    return len(s) < 40 or bool(THIN.search(s)) or s.lower().endswith(("updates", "update.", "regulation 30"))


class Item(BaseModel):
    idx: int
    ref: str = Field(max_length=8)
    category: Category
    sub_type: str | None = Field(default=None, max_length=40)
    materiality: int = Field(ge=0, le=100)
    one_line: str = Field(max_length=200)
    people: list[str] = Field(default_factory=list)
    orgs: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    needs_deep_read: bool = False


class Batch(BaseModel):
    items: list[Item]


SYSTEM = (
    "You triage Indian stock-exchange filings for a long-term equity investor. For each filing "
    "decide its category from this fixed list: " + ", ".join(CATEGORIES) + ". "
    "Definitions: results = quarterly/annual results and their decks; M&A = acquisition, merger, "
    "demerger, JV, stake purchase or sale; fund_raise = equity or debt raising, buyback; "
    "management_change = director/CEO/CFO/KMP joining or leaving; litigation = lawsuits, "
    "regulatory or tax orders, fines; capex = new plant, capacity expansion, commissioning; "
    "press_release = other news such as order wins, products, partnerships, awards, client wins; "
    "investor_meetings = analyst/investor meeting schedules or conferences; unclassified = "
    "routine paperwork. Rate materiality 0-100: how much it could change an investor's view of "
    "the company. Most filings are routine and should score below 30. Write one_line as the fact "
    "with its number, at most 18 words, without repeating the company name or the word 'filing'. "
    "Use only the text given; if something is not stated, leave it out. Return JSON "
    '{"items": [...]} with exactly one item per input filing, in input order, where idx is the '
    "number in square brackets and ref is copied exactly from that filing. Describe only that "
    "filing; never mix details between filings.\n\nExample input:\n[0] ref: a1b2\n"
    "category: General Updates\n"
    "subject: X Limited has informed the Exchange about General Updates\n"
    "text: Sub: Intimation under Regulation 30 - The Board approved setting up a plant with "
    "capacity of 240 KTA at an investment of Rs 2,500 crore.\n"
    "[1] ref: c3d4\ncategory: Updates\nsubject: X Limited has informed the Exchange regarding 'Change in "
    "address of Registrar and Share Transfer Agent'.\n"
    'Example output: {"items": [{"idx": 0, "ref": "a1b2", "category": "capex", "sub_type": null, '
    '"materiality": 70, "one_line": "Board approves 240 KTA plant, Rs 2,500 crore investment", '
    '"people": [], "orgs": [], "amounts": ["Rs 2,500 crore"], "needs_deep_read": true}, '
    '{"idx": 1, "ref": "c3d4", "category": "unclassified", "sub_type": "admin", "materiality": 2, '
    '"one_line": "Registrar and transfer agent changed its office address", "people": [], '
    '"orgs": [], "amounts": [], "needs_deep_read": false}]}'
)


def render_batch(rows: list[dict]) -> str:
    parts = []
    for i, r in enumerate(rows):
        text = salient(r.get("text"))[:TEXT_CHARS].strip()
        parts.append(
            f"[{i}] ref: {r.get('ref') or '-'}\n"
            f"category: {r.get('exch_category') or '-'}\n"
            f"subject: {(r.get('subject') or '-')[:400]}\n" + (f"text: {text}\n" if text else "")
        )
    return "\n".join(parts)


def clip_words(s: str, n: int = ONE_LINE_WORDS) -> str:
    words = s.split()
    return s.strip() if len(words) <= n else " ".join(words[:n]).rstrip(",.;:") + "…"


def to_classified(item: Item, model: str) -> Classified:
    base = round(item.materiality * 0.6)  # model materiality 0–100 → base 0–60 (spec §8.6)
    return Classified(
        item.category, item.sub_type, base, f"model ({model}): {clip_words(item.one_line)}", decided_by="llm"
    )


def ref_for(filing_id: int) -> str:
    """Short per-filing token the model must echo, so a misaligned answer is rejected."""
    import hashlib

    return hashlib.sha256(f"finn-{filing_id}".encode()).hexdigest()[:4]
