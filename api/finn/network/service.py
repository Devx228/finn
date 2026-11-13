"""The Network as render-ready views (spec §9): who can help on a company, second-degree paths to
people named in filings, the expertise map, keep-warm nudges and coverage gaps.

Everything here is code over stored rows — no model call. Contacts are synthetic and labelled;
public figures' facts come only from the exchange filing that named them (source URL kept).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.network import synthetic as syn
from finn.network.graph import TODAY, Emp, Person, label, overlap, paths, warmth, who
from finn.network.resolve import norm_org
from finn.network.store import load_people
from finn.push.brief import clean_subject

# Events where "who can help" earns a place on the card (brief: material events + mgmt change).
MATERIAL = {"M&A", "capex", "litigation", "fund_raise", "management_change", "results", "credit_rating"}

QUESTIONS = {
    "management_change": [
        "What is {who}'s reputation for execution, and how do they run a team in the first year?",
        "Who else was considered internally, and does this change the bench below the top?",
        "Which priorities of the outgoing leader are likely to change?",
    ],
    "M&A": [
        "How has {co} integrated past acquisitions — what went wrong, what worked?",
        "Does the target fit the core business or is it a new capability bet?",
        "What would the peers you know read into this deal?",
    ],
    "capex": [
        "Is the industry adding capacity at the same time — any risk of oversupply?",
        "How long do projects like this usually take to ramp, and where do they slip?",
        "How is it being funded: internal accruals or new debt?",
    ],
    "litigation": [
        "How material is this kind of order in the sector, and how do they usually end?",
        "Is this specific to {co} or an industry-wide regulatory push?",
        "What would a reasonable worst case look like?",
    ],
    "fund_raise": [
        "Why raise now — growth, balance-sheet repair or regulatory capital?",
        "Who are the likely buyers and at what discount?",
        "Does this change the dividend or capex plans?",
    ],
    "results": [
        "Which line moved most this quarter, and is it one-off or a trend?",
        "How are peers seeing demand and pricing in the same quarter?",
        "Where does the street usually misread {co}'s quarterly numbers?",
    ],
    "credit_rating": [
        "What drove the rating action, and is the agency's view moving across the sector?",
        "Does this change {co}'s borrowing cost meaningfully?",
        "What would trigger the next action?",
    ],
}


def _theme_lookup() -> dict[str, str]:
    out = {}
    for theme, orgs in syn.THEME_ORGS.items():
        for o in orgs:
            out[norm_org(o)] = theme
    return out


THEME_BY_NORM = _theme_lookup()


def org_theme(name: str, industry: str | None) -> str | None:
    if industry in syn.THEME_ORGS:
        return industry
    n = norm_org(name)
    if n in THEME_BY_NORM:
        return THEME_BY_NORM[n]
    for k, t in THEME_BY_NORM.items():  # "icici bank" ⊂ "icici bank limited"
        if len(k) > 4 and (n.startswith(k) or k.startswith(n)) and len(n) > 4:
            return t
    return None


def _fmt_span(s: date | None, e: date | None) -> str:
    if not s and not e:
        return ""
    return f"{s.year if s else '?'}–{e.year if e and e < TODAY else 'now'}"


def _contact_json(p: Person) -> dict:
    w, wev = warmth(p)
    cur = next((e for e in p.emps if e.end is None), p.emps[-1] if p.emps else None)
    return {
        "id": p.id,
        "name": p.name,
        "synthetic": p.is_synthetic,
        "headline": f"{cur.title}, {cur.org}" if cur else None,
        "how_known": p.how_known,
        "last_contact": p.last_contact.isoformat() if p.last_contact else None,
        "warmth": w,
        "warmth_label": label(w),
        "warmth_why": wev,
    }


def _career_json(p: Person) -> list[dict]:
    emps = sorted(p.emps, key=lambda e: e.start or date(1900, 1, 1))
    if p.is_synthetic:
        return [
            {"org": e.org, "title": e.title, "span": _fmt_span(e.start, e.end), "current": e.end is None}
            for e in emps
        ]
    # a real person's record says only what the filing says: an end the filing doesn't give is never shown
    return [
        {
            "org": e.org,
            "title": e.title,
            "span": (
                f"from {e.start.year} (term to {e.end.year})"
                if e.start and e.end and e.end > TODAY
                else f"{e.start.year}–{e.end.year}"
                if e.start and e.end
                else f"from {e.start.year}"
                if e.start
                else "years not stated"
            ),
            "current": e.end is None and not e.open_unknown,
        }
        for e in emps
    ]


def _worked_at(why: str) -> str | None:
    """'worked at peer Hindustan Unilever as CHRO (2018–now); …' → 'Hindustan Unilever'."""
    import re

    m = re.match(r"worked at (?:peer )?(.+?) as ", why)
    return m.group(1).replace(" Limited", "") if m else None


GENERIC_ORG_WORDS = {
    "limited",
    "ltd",
    "ltd.",
    "private",
    "pvt",
    "pvt.",
    "the",
    "of",
    "and",
    "&",
    "india",
    "inc",
    "inc.",
}


def _org_phrase(org: str) -> str:
    """The words a bio would use for this employer: its first two distinctive words ('ICICI Bank',
    'ICICI Prudential'); one word if that's all there is."""
    words = [w for w in org.replace(",", " ").split() if w.lower() not in GENERIC_ORG_WORDS]
    return " ".join(words[:2]).lower()


def clean_public_careers(
    conn: Connection, people: dict[int, Person], mentions: dict[int, list[dict]]
) -> dict:
    """Careers of real people come from what their filing states, nothing more.
    1. A bio span is kept only if one sentence of the filing names that employer and that year
       ("A member of the ICICI Group since 1992" does not put someone at ICICI Bank in 1992).
    2. An open span closes when the person joins their next stated employer; with no later employer
       its end is unknown: shown "from <year>" and never counted as overlap.
    The role at the filing company itself (the appointment) is kept as filed."""
    import dataclasses
    import re

    pub = {pid: p for pid, p in people.items() if not p.is_synthetic and p.kind != "contact"}
    fids = sorted({m["filing_id"] for pid in pub for m in mentions.get(pid, [])})
    texts: dict[int, str] = {}
    own_orgs: dict[int, set[int]] = {}
    if fids:
        for fid, pages, oid in conn.execute(
            "SELECT f.id, f.text_pages, o.id FROM filings f LEFT JOIN orgs o ON o.company_id = f.company_id "
            "WHERE f.id = ANY(%s)",
            (fids,),
        ).fetchall():
            texts[fid] = re.sub(r"\s+", " ", " ".join(pages or []))
            if oid:
                own_orgs.setdefault(fid, set()).add(oid)
    counts = {"dropped": 0, "closed": 0, "open_unknown": 0, "years_not_stated": 0}
    for pid, p in pub.items():
        ms = mentions.get(pid, [])
        text = " ".join(texts.get(m["filing_id"], "") for m in ms)
        current = set().union(*(own_orgs.get(m["filing_id"], set()) for m in ms)) if ms else set()
        # don't break a sentence at an abbreviation ("Cummins Inc. Components Group from 2010")
        guarded = re.sub(r"\b(Inc|Ltd|Co|Pvt|Corp|Mr|Ms|Mrs|Dr|No|St)\.", r"\1", text)
        sentences = re.split(r"(?<=[.;])\s+", guarded) if text else []
        kept = []
        for e in p.emps:
            if e.org_id in current or not sentences or e.start is None:
                kept.append(e)
                continue
            phrase = _org_phrase(e.org)
            years = {str(e.start.year)} | ({str(e.end.year)} if e.end else set())
            # whole words only: "bank" must not match "banking"
            words = [
                re.compile(rf"(?<![a-z0-9]){re.escape(w.strip('.'))}(?![a-z0-9])") for w in phrase.split()
            ]
            if any(all(w.search(s.lower()) for w in words) and any(y in s for y in years) for s in sentences):
                kept.append(e)
            elif any(all(w.search(s.lower()) for w in words) for s in sentences):
                # the filing names the employer but not when: keep it, with no years
                kept.append(dataclasses.replace(e, start=None, end=None))
                counts["years_not_stated"] += 1
            else:
                counts["dropped"] += 1
        uniq: dict[tuple, Emp] = {}
        for e in kept:  # the same span extracted twice is one span
            uniq.setdefault((e.org_id, e.start, e.end, (e.title or "")[:40]), e)
        kept = sorted(uniq.values(), key=lambda e: e.start or date(1900, 1, 1))
        for i, e in enumerate(kept):
            if e.end is not None or e.org_id in current:
                continue
            nxt = next(
                (
                    x
                    for x in kept[i + 1 :]
                    if x.start and e.start and x.start > e.start and x.org_id != e.org_id
                ),
                None,
            )
            if nxt is not None:
                e.end = nxt.start
                counts["closed"] += 1
            else:
                e.open_unknown = True
                counts["open_unknown"] += 1
        p.emps = kept
    return counts


@dataclass
class YouOverlap:
    org: str
    span: str


class Net:
    """Loads the tenant's network once; answers every question from memory."""

    def __init__(self, conn: Connection, tenant: int = syn.TENANT) -> None:
        self.people = load_people(conn, tenant=tenant)
        self.contacts = [p for p in self.people.values() if p.kind == "contact"]
        orgs = conn.execute(
            "SELECT o.id, o.canonical_name, o.industry, c.nse_symbol FROM orgs o "
            "LEFT JOIN companies c ON c.id = o.company_id"
        ).fetchall()
        self.org_name = {oid: n for oid, n, _, _ in orgs}
        self.org_theme = {oid: org_theme(n, ind) for oid, n, ind, _ in orgs}
        self.org_by_symbol = {sym: oid for oid, _, _, sym in orgs if sym}
        self.by_theme: dict[str, set[int]] = defaultdict(set)
        for oid, t in self.org_theme.items():
            if t:
                self.by_theme[t].add(oid)
        # Mentions: who was named in which filing, with the source URL.
        self.mentions: dict[int, list[dict]] = defaultdict(list)
        self.filing_people: dict[int, list[dict]] = defaultdict(list)
        for fid, pid, role, event, url, sym, ts in conn.execute(
            "SELECT m.filing_id, m.person_id, m.role, m.event, f.pdf_url, c.nse_symbol, f.ts_ist "
            "FROM person_mentions m JOIN filings f ON f.id = m.filing_id "
            "JOIN companies c ON c.id = f.company_id ORDER BY f.ts_ist DESC"
        ).fetchall():
            m = {
                "filing_id": fid,
                "person_id": pid,
                "role": role,
                "event": event,
                "url": url,
                "symbol": sym,
                "ts": ts.isoformat(),
            }
            self.mentions[pid].append(m)
            self.filing_people[fid].append(m)
        clean_public_careers(conn, self.people, self.mentions)
        # the investor's own meeting notes (synthetic, labelled), newest first, per company symbol
        self.notes: dict[str, list[dict]] = defaultdict(list)
        for day, sym, pids, notes, tags in conn.execute(
            "SELECT m.date, c.nse_symbol, m.person_ids, m.notes, m.tags FROM meetings m "
            "JOIN companies c ON c.id = m.company_id ORDER BY m.date DESC"
        ).fetchall():
            self.notes[sym].append(
                {"date": day, "person_ids": list(pids or []), "notes": notes, "tags": tags}
            )
        # the Promise Ledger's own summary line per researched company (only reviewed ledgers)
        self.promises: dict[str, dict] = {}
        for _key, body in conn.execute(
            "SELECT key, body FROM views WHERE key LIKE 'research:%%' AND key <> 'research:index'"
        ).fetchall():
            ledger = body.get("ledger") or {}
            groups = [g for g in body.get("groups") or [] if g.get("resolved")]
            if not ledger.get("pattern") or not (body.get("provenance") or {}).get("reviewed"):
                continue
            g = groups[0] if groups else None
            self.promises[body["symbol"]] = {
                "pattern": ledger["pattern"],
                "line": (g["verdicts"][0]["line"] if g and g.get("verdicts") else None),
                "title": g["title"] if g else None,
                "href": f"/research?s={body['symbol']}" + (f"&fy={g['period']}" if g else ""),
            }
        inv = syn.investor()
        self.you = [(o, s, e) for o, _, s, e in inv["employers"]]
        self.you_edu = [(i, d, ey) for i, d, _, ey in inv["alma_maters"]]

    # ---- company -------------------------------------------------------------------------
    def who_for(self, symbol: str, event: str | None = None, top: int = 3) -> list[dict]:
        oid = self.org_by_symbol.get(symbol)
        if oid is None:
            return []
        theme = self.org_theme.get(oid)
        peers = (self.by_theme.get(theme or "", set()) - {oid}) if theme else set()
        company = self.org_name[oid]
        out = []
        for c in who(oid, peers, set(), self.contacts, event, company, top):
            out.append(
                {
                    **_contact_json(c.person),
                    "relevance": c.relevance,
                    "rank": c.rank,
                    "why": c.why,
                    "what_theyd_know": c.what_theyd_know,
                    "compliance": c.compliance,
                }
            )
        return out

    # ---- people named in filings -----------------------------------------------------------
    def you_overlap(self, target: Person) -> list[str]:
        out = []
        for org, s, e in self.you:
            spans = []
            for t in target.emps:
                if norm_org(t.org) != norm_org(org) and not norm_org(t.org).startswith(norm_org(org)):
                    continue
                if t.start is None or t.open_unknown:
                    continue
                a, b = max(s, t.start), min(e or TODAY, t.end or TODAY)
                if (b - a).days >= 365:  # a year or more: months in a filing are often unstated
                    spans.append((a, b))
            if spans:
                a, b = min(x[0] for x in spans), max(x[1] for x in spans)
                out.append(
                    f"You were at {org} {a.year}–{b.year if b < TODAY else 'now'} while they were there"
                )
        for inst, _, _ey in self.you_edu:
            for d in target.edus:
                if norm_org(d.org) == norm_org(inst):
                    out.append(f"You both studied at {inst}")
        return out

    def person_view(self, pid: int) -> dict:
        p = self.people[pid]
        ps = paths(p, self.contacts, top=3)
        ms = self.mentions.get(pid, [])
        return {
            "id": pid,
            "name": p.name,
            "kind": p.kind,
            "synthetic": p.is_synthetic,
            "career": _career_json(p),
            "education": [{"institution": d.org, "degree": d.degree, "year": d.end_y} for d in p.edus],
            "you": self.you_overlap(p),
            "paths": [
                {
                    "via": _contact_json(x.contact),
                    "overlap": x.overlap,
                    "overlap_label": label(x.overlap),
                    "strength": x.score,
                    "strength_label": label(min(1.0, x.score * 2)),
                    "evidence": overlap(x.contact, p)[1][:2],
                    "sentence": x.sentence,
                }
                for x in ps
            ],
            "mentions": ms[:4],
            "source": "Profile as disclosed in the company's exchange filing (SEBI requires a brief "
            "profile on appointment). Links go to NSE.",
        }

    # ---- for a brief item ------------------------------------------------------------------
    def last_note(self, symbol: str, people: list[int] | None = None) -> dict | None:
        """The investor's most recent meeting note on this company; one with any of `people`
        present wins. Date, who was there and the note itself, exactly as stored."""
        notes = self.notes.get(symbol) or []
        if not notes:
            return None
        pick = next((n for n in notes if people and set(n["person_ids"]) & set(people)), notes[0])
        names = [self.people[i].name for i in pick["person_ids"] if i in self.people]
        return {"date": pick["date"].isoformat(), "with": names, "text": pick["notes"]}

    def opener(
        self,
        contact: dict,
        company: str,
        fact: str | None,
        when: str | None,
        current: bool,
        where: str | None = None,
    ) -> str:
        """A reconnect message assembled from stored facts only: their name, when you last spoke,
        the filing (its own one-line fact and date). Current employees get a public-only note."""
        first = contact["name"].split()[0]
        last = contact.get("last_contact")
        since = f" since we spoke in {date.fromisoformat(last):%B}" if last else ""
        co = company.replace(" Limited", "")
        if fact and len(fact) > 140:  # end on a word, never mid-number
            fact = fact[:140].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        about = (
            f"{co}'s filing{f' on {when}' if when else ''}: {fact.rstrip('.')}"
            + ("" if fact.endswith("…") else ".")
            if fact
            else f"{co}'s latest filing."
        )
        # only say why they'd know what the record says: where they actually worked
        ask = (
            "I'd value 15 minutes on how the industry sees it, only what's public of course."
            if current
            else f"I'd value 15 minutes of your view on it, given your time at {where}."
            if where
            else "I'd value 15 minutes of your view on it."
        )
        return f"Hi {first}, it's been a while{since}. I was reading {about} {ask} Would this week work?"

    def for_item(
        self,
        symbol: str,
        category: str,
        filing_ids: list[int],
        company: str,
        fact: str | None = None,
        when: str | None = None,
    ) -> dict | None:
        if category not in MATERIAL:
            return None
        named = []
        seen = set()
        for fid in filing_ids:
            for m in self.filing_people.get(fid, []):
                if m["person_id"] in seen:
                    continue
                seen.add(m["person_id"])
                v = self.person_view(m["person_id"])
                named.append({**v, "role": m["role"], "event": m["event"]})
        # incoming people first: they are the ones you don't know yet
        named.sort(key=lambda v: (v["event"] not in ("appointment", "re-designation"), -len(v["paths"])))
        call = self.who_for(symbol, category, top=3)
        if not named and not call:
            return None
        lead = named[0]["name"] if named else None
        qs = [
            q.format(who=lead or "the new appointee", co=company.replace(" Limited", ""))
            for q in QUESTIONS.get(category, [])
        ]
        best = call[0] if call else None
        best_path = next((v["paths"][0] for v in named if v["paths"]), None)
        points = 0
        if best_path:
            points = max(points, round(10 * min(1.0, best_path["strength"] * 2)))
        if best:
            points = max(points, round(10 * min(1.0, best["rank"])))
        if any(v["you"] for v in named):
            points = max(points, 8)
        out = {"people": named[:3], "call": call, "questions": qs, "points": points}
        note = self.last_note(symbol, [c["id"] for c in call])
        if note:
            out["note"] = note
        if symbol in self.promises:
            out["promise"] = self.promises[symbol]
        if best:
            out["opener"] = {
                "to": best["name"],
                "text": self.opener(
                    best, company, fact, when, bool(best.get("compliance")), _worked_at(best.get("why", ""))
                ),
            }
        return out

    # ---- the People tab ---------------------------------------------------------------------
    def expertise(self) -> list[dict]:
        rows = []
        for theme in syn.THEME_ORGS:
            orgs = self.by_theme.get(theme, set())
            ranked = []
            for c in self.contacts:
                yrs = sum(
                    ((e.end or TODAY) - (e.start or TODAY)).days / 365 for e in c.emps if e.org_id in orgs
                )
                if yrs >= 1:
                    w, _ = warmth(c)
                    ranked.append((yrs * (0.5 + w), yrs, c))
            ranked.sort(key=lambda x: -x[0])
            if ranked:
                rows.append(
                    {
                        "theme": theme,
                        "count": len(ranked),
                        "people": [
                            {
                                **_contact_json(c),
                                "years": round(y, 1),
                                "orgs": sorted({e.org for e in c.emps if e.org_id in orgs}),
                            }
                            for _, y, c in ranked[:4]
                        ],
                    }
                )
        return sorted(rows, key=lambda r: -r["count"])

    def keep_warm(self, conn: Connection, now: datetime, days: int = 30) -> list[dict]:
        """Cold contacts (> 4 months) whose current or former employer filed something material
        recently — a natural reason to reconnect."""
        events = conn.execute(
            "SELECT c.nse_symbol, k.category, f.ts_ist, coalesce(nullif(k.one_line, ''), f.subject), "
            "f.pdf_url FROM filings f JOIN filing_class k ON k.filing_id = f.id "
            "JOIN companies c ON c.id = f.company_id WHERE f.ts_ist >= %s AND k.category = ANY(%s) "
            "AND coalesce(k.base, 0) >= 40 ORDER BY f.ts_ist DESC",
            (now - timedelta(days=days), list(MATERIAL)),
        ).fetchall()
        latest: dict[str, tuple] = {}
        for sym, cat, ts, subj, url in events:
            latest.setdefault(sym, (cat, ts, subj, url))
        out = []
        for c in self.contacts:
            if not c.last_contact or (TODAY - c.last_contact).days < 120:
                continue
            for e in c.emps:
                sym = next((s for s, o in self.org_by_symbol.items() if o == e.org_id), None)
                if sym and sym in latest:
                    cat, ts, subj, url = latest[sym]
                    out.append(
                        {
                            **_contact_json(c),
                            "symbol": sym,
                            "org": e.org,
                            "relation": "works there"
                            if e.end is None
                            else f"worked there until {e.end.year}",
                            "event": cat,
                            "event_label": cat.replace("_", " "),
                            "event_ts": ts.isoformat(),
                            "event_text": clean_subject(subj)[:140],
                            "url": url,
                            "months_cold": (TODAY - c.last_contact).days // 30,
                            "opener": self.opener(
                                _contact_json(c),
                                self.org_name.get(e.org_id, e.org),
                                clean_subject(subj),
                                f"{ts:%d %b}",
                                e.end is None,
                                e.org.replace(" Limited", ""),
                            ),
                        }
                    )
                    break
        out.sort(key=lambda x: (-x["warmth"], x["months_cold"]))
        return out[:8]

    def coverage(self, conn: Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT c.nse_symbol, c.name, h.weight_pct FROM holdings h "
            "JOIN companies c ON c.id = h.company_id ORDER BY h.weight_pct DESC"
        ).fetchall()
        out = []
        for sym, name, wt in rows:
            ws = self.who_for(sym, top=5)
            direct = [
                w for w in ws if w["why"].startswith("worked at " + name) or "worked at " + name in w["why"]
            ]
            out.append(
                {
                    "symbol": sym,
                    "name": name,
                    "weight_pct": float(wt),
                    "direct": len(direct),
                    "adjacent": len(ws) - len(direct),
                    "best": ws[0] if ws else None,
                }
            )
        return out

    def directory(self) -> list[dict]:
        """Every contact with what a free-text "who knows X" can match on: career (orgs, titles,
        years), the themes of those orgs, and the listed companies they map to. Searched in the
        browser; no model."""
        sym_by_org = {self.org_name[o].lower(): s for s, o in self.org_by_symbol.items()}
        out = []
        for p in self.contacts:
            career = _career_json(p)
            themes = sorted({t for e in p.emps if (t := org_theme(e.org, None))})
            out.append(
                {
                    **_contact_json(p),
                    "career": career,
                    "themes": themes,
                    "symbols": sorted({s for e in p.emps if (s := sym_by_org.get(e.org.lower()))}),
                }
            )
        return out

    def figures(self) -> list[dict]:
        out = []
        for pid, ms in self.mentions.items():
            m = next((x for x in ms if x["event"] in ("appointment", "re-designation")), None)
            if m is None:  # "new faces": people arriving, not leaving
                continue
            v = self.person_view(pid)
            out.append(
                {
                    "id": pid,
                    "name": v["name"],
                    "symbol": m["symbol"],
                    "role": m["role"],
                    "event": m["event"],
                    "ts": m["ts"],
                    "paths": len(v["paths"]),
                    "best": v["paths"][0] if v["paths"] else None,
                    "you": v["you"],
                }
            )
        out.sort(key=lambda f: -(f["best"]["strength"] if f["best"] else 0) - (0.3 if f["you"] else 0))
        return out


def materialise(conn: Connection, now: datetime) -> dict[str, int]:
    net = Net(conn)
    views: dict[str, dict] = {}
    cov = net.coverage(conn)
    views["network:home"] = {
        "as_of": now.isoformat(),
        "contacts": len(net.contacts),
        "synthetic_note": "Contacts, their careers and meetings are synthetic (fictional people at real "
        "organisations). Executives' profiles come from NSE filings.",
        "keep_warm": net.keep_warm(conn, now),
        "figures": net.figures(),
        "expertise": net.expertise(),
        "coverage": cov,
        "directory": net.directory(),
    }
    for sym in net.org_by_symbol:
        views[f"network:company:{sym}"] = {
            "symbol": sym,
            "company": net.org_name[net.org_by_symbol[sym]],
            "who": net.who_for(sym, top=5),
            "people": [f for f in views["network:home"]["figures"] if f["symbol"] == sym],
        }
    for pid in net.mentions:
        views[f"network:person:{pid}"] = net.person_view(pid)
    for k, body in views.items():
        conn.execute(
            "INSERT INTO views (key, body, as_of) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE "
            "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
            (k, Jsonb(body), now),
        )
    conn.commit()
    return {"views": len(views)}
