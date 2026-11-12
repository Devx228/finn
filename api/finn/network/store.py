"""Load the synthetic network into Postgres, plant overlaps with real executives, and read
people back as graph.Person objects."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta

from psycopg import Connection

from finn.network import synthetic as syn
from finn.network.graph import Edu, Emp, Person
from finn.network.resolve import OrgIndex, norm_person, resolve_org


def _theme_of(org: str) -> str | None:
    return next((t for t, orgs in syn.THEME_ORGS.items() if org in orgs), None)


def reset_tenant(conn: Connection, tenant: int = syn.TENANT) -> None:
    """Remove this tenant's synthetic network (contacts, relationships, meetings)."""
    conn.execute("DELETE FROM meetings WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM relationships WHERE tenant_id = %s", (tenant,))
    conn.execute("DELETE FROM persons WHERE tenant_id = %s", (tenant,))


def _insert_contact(conn: Connection, idx: OrgIndex, c: syn.Contact, source: str) -> int:
    pid = conn.execute(
        "INSERT INTO persons (tenant_id, kind, full_name, name_norm, headline, city, is_synthetic, "
        "source) VALUES (%s, 'contact', %s, %s, %s, %s, true, %s) RETURNING id",
        (syn.TENANT, c.name, norm_person(c.name), f"{c.jobs[-1].title}, {c.jobs[-1].org}", c.city, source),
    ).fetchone()[0]  # type: ignore[index]
    for j in c.jobs:
        oid = resolve_org(conn, idx, j.org, industry=_theme_of(j.org))
        conn.execute(
            "INSERT INTO employments (person_id, org_id, title, function, seniority, start_ym, end_ym) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (pid, oid, j.title, j.function, j.seniority, j.start, j.end),
        )
    for inst, deg, sy, ey in c.edu:
        oid = resolve_org(conn, idx, inst, kind="institution")
        conn.execute(
            "INSERT INTO educations (person_id, institution_org_id, degree, start_y, end_y) "
            "VALUES (%s,%s,%s,%s,%s)",
            (pid, oid, deg, sy, ey),
        )
    conn.execute(
        "INSERT INTO relationships (tenant_id, contact_id, how_known, since_ym, last_contact_date, "
        "interactions_24m, closeness) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (syn.TENANT, pid, c.how_known, c.since, c.last_contact, c.interactions_24m, c.closeness),
    )
    for t in c.themes:
        conn.execute(
            "INSERT INTO expertise (person_id, theme, score, evidence) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (
                pid,
                t,
                round(sum(((j.end or syn.TODAY) - j.start).days for j in c.jobs) / 365, 1),
                "; ".join(f"{j.title}, {j.org}" for j in c.jobs),
            ),
        )
    return pid


def load_synthetic(conn: Connection) -> dict[str, int]:
    reset_tenant(conn)
    idx = OrgIndex.load(conn)
    cs = syn.contacts()
    ids = {c.name: _insert_contact(conn, idx, c, "synthetic generator") for c in cs}
    company_by_org: dict[str, int] = dict(
        conn.execute(
            "SELECT o.canonical_name, o.company_id FROM orgs o WHERE o.company_id IS NOT NULL"
        ).fetchall()
    )
    for org, d, attendees, note, tags in syn.meetings(cs):
        conn.execute(
            "INSERT INTO meetings (tenant_id, date, company_id, person_ids, notes, tags) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (syn.TENANT, d, company_by_org.get(org), [ids[a] for a in attendees if a in ids], note, tags),
        )
    conn.commit()
    return {"contacts": len(cs), "meetings": len(syn.meetings(cs))}


def seed_overlaps(conn: Connection) -> dict[str, int]:
    """Plant synthetic contacts whose careers overlap real executives' disclosed careers
    (spec §4.3). Each planted contact is synthetic and labelled; the executive's facts come only
    from the filing. One former colleague (overlapping years, same org) per executive with a
    disclosed prior employer, plus one classmate where an institution is disclosed."""
    r = random.Random(syn.SEED + 7)
    idx = OrgIndex.load(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT p.id, p.full_name, o.canonical_name, e.start_ym, e.end_ym, e.title
        FROM persons p JOIN person_mentions m ON m.person_id = p.id
        JOIN employments e ON e.person_id = p.id JOIN orgs o ON o.id = e.org_id
        WHERE p.kind = 'public_figure' AND m.event IN ('appointment', 're-designation')
          AND e.start_ym IS NOT NULL
        """
    ).fetchall()
    planted = 0
    seen: set[tuple[int, str]] = set()
    for pid, pname, org, start, end, title in rows:
        if (pid, org) in seen:
            continue
        seen.add((pid, org))
        s = max(start, date(2005, 1, 1))
        e = end or syn.TODAY
        if (e - s).days < 400:
            continue
        name = None
        while (
            not name
            or conn.execute("SELECT 1 FROM persons WHERE name_norm = %s", (norm_person(name),)).fetchone()
        ):
            name = f"{r.choice(syn.FIRST)} {r.choice(syn.LAST)}"
        cs = s + timedelta(days=r.randint(0, 200))
        ce = min(e, cs + timedelta(days=r.randint(900, 1800)))
        func = "finance" if title and "financ" in title.lower() else "general-management"
        c = syn.Contact(
            name=name,
            city="Mumbai",
            jobs=[
                syn.Job(org, "Senior Vice President", func, 4, cs, ce if ce < syn.TODAY else None),
                syn.Job(
                    r.choice(syn.THEME_ORGS["markets"]),
                    "Director",
                    "strategy",
                    4,
                    ce + timedelta(days=60),
                    None,
                ),
            ],
            edu=[("IIM Ahmedabad", "MBA", cs.year - 6, cs.year - 4)],
            how_known=r.choice(["ex-colleague", "industry-friend", "met-as-management"]),
            since=date(2016, r.randint(1, 12), 1),
            last_contact=syn.TODAY - timedelta(days=r.randint(20, 400)),
            interactions_24m=r.randint(2, 8),
            closeness=r.randint(3, 5),
            themes=[],
        )
        c.jobs = [j for j in c.jobs if j.start < syn.TODAY]
        _insert_contact(conn, idx, c, f"seed_overlaps: overlaps {pname} at {org}")
        planted += 1
    conn.commit()
    return {"overlap_contacts": planted}


def load_people(
    conn: Connection, ids: list[int] | None = None, tenant: int = syn.TENANT
) -> dict[int, Person]:
    q = (
        "SELECT p.id, p.full_name, p.kind, p.is_synthetic, r.how_known, r.since_ym, r.last_contact_date, "
        "r.interactions_24m, r.closeness FROM persons p LEFT JOIN relationships r "
        "ON r.contact_id = p.id AND r.tenant_id = %s WHERE (p.tenant_id = %s OR p.tenant_id IS NULL)"
    )
    args: list = [tenant, tenant]
    if ids is not None:
        q += " AND p.id = ANY(%s)"
        args.append(ids)
    people = {
        pid: Person(
            pid,
            name,
            kind,
            syn_,
            how_known=hk,
            since=since,
            last_contact=last,
            interactions_24m=n or 0,
            closeness=cl or 0,
        )
        for pid, name, kind, syn_, hk, since, last, n, cl in conn.execute(q, args).fetchall()
    }
    emps = defaultdict(list)
    for pid, oid, org, title, fn, sen, s, e in conn.execute(
        "SELECT e.person_id, e.org_id, o.canonical_name, e.title, e.function, e.seniority, e.start_ym, "
        "e.end_ym FROM employments e JOIN orgs o ON o.id = e.org_id WHERE e.person_id = ANY(%s)",
        (list(people),),
    ).fetchall():
        emps[pid].append(Emp(oid, org, title, fn, sen, s, e))
    for pid, oid, org, deg, ey in conn.execute(
        "SELECT d.person_id, d.institution_org_id, o.canonical_name, d.degree, d.end_y FROM educations d "
        "JOIN orgs o ON o.id = d.institution_org_id WHERE d.person_id = ANY(%s)",
        (list(people),),
    ).fetchall():
        people[pid].edus.append(Edu(oid, org, deg, ey))
    for pid, es in emps.items():
        people[pid].emps = es
    return people
