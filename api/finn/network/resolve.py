"""Entity resolution (spec §7.6): organisations and people.

Organisations: normalise (case, legal suffixes, punctuation) → exact alias → fuzzy (token-set
ratio ≥ 92) → else create, flagged unreviewed. People: a name alone is never enough — name
similarity is combined with corroboration (shared organisation with overlapping years, matching
role family, shared institution). ≥ 0.9 same person; 0.6–0.9 "possible match", never merged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from psycopg import Connection
from rapidfuzz import fuzz

SUFFIXES = re.compile(
    r"\b(limited|ltd|pvt|private|inc|incorporated|llp|plc|corporation|corp|co|company|india|"
    r"the|group|holdings?)\b",
    re.I,
)
HONORIFICS = re.compile(r"^(mr|mrs|ms|dr|prof|shri|smt|cdr|capt|col|sri)\.?\s+", re.I)
FUZZY_ORG = 92


def norm_org(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = SUFFIXES.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_person(name: str) -> str:
    s = name.strip()
    while HONORIFICS.match(s):
        s = HONORIFICS.sub("", s)
    s = re.sub(r"\(.*?\)", " ", s)  # "(DIN: 123)"
    s = re.sub(r"[^A-Za-z ]", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str, b: str) -> float:
    """0–1. Handles order and initials: 'K C Jhanwar' ~ 'Kailash Chandra Jhanwar'."""
    x, y = norm_person(a).split(), norm_person(b).split()
    if not x or not y:
        return 0.0
    if x[-1] != y[-1] and x[0] != y[-1] and x[-1] != y[0]:  # surnames must agree (any order)
        return round(fuzz.token_set_ratio(" ".join(x), " ".join(y)) / 100 * 0.6, 2)
    xs, ys = set(x), set(y)
    if xs == ys:
        return 1.0
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    initials_ok = all(any(t == w or (len(t) == 1 and w.startswith(t)) for w in long_) for t in short)
    return 0.95 if initials_ok else round(fuzz.token_set_ratio(" ".join(x), " ".join(y)) / 100 * 0.9, 2)


@dataclass
class OrgIndex:
    by_norm: dict[str, int]
    names: dict[int, str]

    @classmethod
    def load(cls, conn: Connection) -> OrgIndex:
        by_norm: dict[str, int] = {}
        names: dict[int, str] = {}
        for oid, canon, aliases in conn.execute("SELECT id, canonical_name, aliases FROM orgs").fetchall():
            names[oid] = canon
            for a in [canon, *aliases]:
                by_norm.setdefault(norm_org(a), oid)
        return cls(by_norm, names)

    def find(self, name: str) -> tuple[int | None, float]:
        n = norm_org(name)
        if not n:
            return None, 0.0
        if n in self.by_norm:
            return self.by_norm[n], 1.0
        best, score = None, 0.0
        for k, oid in self.by_norm.items():
            s = fuzz.token_set_ratio(n, k)
            if s > score:
                best, score = oid, s
        return (best, score / 100) if score >= FUZZY_ORG else (None, score / 100)


def resolve_org(
    conn: Connection,
    idx: OrgIndex,
    name: str,
    *,
    kind: str = "company",
    company_id: int | None = None,
    industry: str | None = None,
) -> int:
    oid, _ = idx.find(name)
    if oid is not None:
        return oid
    row = conn.execute(
        "INSERT INTO orgs (canonical_name, kind, company_id, industry, unreviewed) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (canonical_name) DO UPDATE SET "
        "canonical_name = EXCLUDED.canonical_name RETURNING id",
        (name.strip(), kind, company_id, industry, company_id is None),
    ).fetchone()
    assert row is not None
    idx.by_norm[norm_org(name)] = row[0]
    idx.names[row[0]] = name.strip()
    return row[0]
