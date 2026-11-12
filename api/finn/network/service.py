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
from finn.network.graph import TODAY, Person, label, overlap, paths, warmth, who
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
    return [
        {"org": e.org, "title": e.title, "span": _fmt_span(e.start, e.end), "current": e.end is None}
        for e in emps
    ]


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
                if t.start is None:
                    continue
                a, b = max(s, t.start), min(e or TODAY, t.end or TODAY)
                if a < b:
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
    def for_item(self, symbol: str, category: str, filing_ids: list[int], company: str) -> dict | None:
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
        return {"people": named[:3], "call": call, "questions": qs, "points": points}

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
