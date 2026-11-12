"""Management-change extraction (spec §8.4): the appointee's brief profile comes from the filing
itself (SEBI requires one). BULK model extracts; code verifies every name and organisation
appears in the filing text and drops anything that doesn't.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from finn.push.classify_llm import salient

PROMPT_VERSION = "extract_appointment-v1"
TEXT_CHARS = 9000


class Edu(BaseModel):
    institution: str
    degree: str | None = None
    year: int | None = None


class Job(BaseModel):
    org: str
    role: str | None = None
    from_year: int | None = None
    to_year: int | None = None


class Change(BaseModel):
    event: Literal[
        "appointment", "resignation", "cessation", "re-designation", "re-appointment", "retirement", "other"
    ]
    person_name: str
    role: str | None = None
    effective_date: str | None = Field(default=None, description="YYYY-MM-DD if stated")
    reason_given: str | None = None
    education: list[Edu] = Field(default_factory=list)
    career: list[Job] = Field(default_factory=list)
    years_experience: int | None = None


class Extraction(BaseModel):
    changes: list[Change]


SYSTEM = (
    "From this Indian stock-exchange filing about a change in directors or management, extract "
    "every person who is appointed, resigns, retires, ceases or is re-designated. For each, copy "
    "their role and effective date, the reason if one is given, and their profile exactly as "
    "disclosed: education (institution, degree, year) and each career position (organisation, "
    "role, from year, to year). Do not add anything not in the text; leave fields empty when not "
    "stated. Ignore the company secretary who signs the letter unless they are the one changing. "
    'Return JSON {"changes": [...]}.'
)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower())).strip()


def appears(needle: str, hay_norm: str) -> bool:
    """True if the (normalised) name appears in the text, allowing honorific/initial noise."""
    n = norm(needle)
    if not n:
        return False
    if n in hay_norm:
        return True
    words = [w for w in n.split() if len(w) > 2 and w not in {"ltd", "limited", "the", "and"}]
    return bool(words) and all(w in hay_norm for w in words)


def input_text(pages: list[str]) -> str:
    return salient(" ".join(pages))[:TEXT_CHARS]


def verify(x: Extraction, text: str) -> tuple[list[Change], list[str]]:
    """Keep only people and organisations that appear in the filing text."""
    hay = norm(text)
    kept, dropped = [], []
    for c in x.changes:
        if not appears(c.person_name, hay):
            dropped.append(f"person not in text: {c.person_name}")
            continue
        jobs = [j for j in c.career if appears(j.org, hay)]
        dropped += [f"org not in text: {j.org}" for j in c.career if j not in jobs]
        edus = [e for e in c.education if appears(e.institution, hay)]
        dropped += [f"institution not in text: {e.institution}" for e in c.education if e not in edus]
        kept.append(c.model_copy(update={"career": jobs, "education": edus}))
    return kept, dropped
