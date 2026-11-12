"""Public figures from management-change filings: extract → verify → resolve → store."""

from __future__ import annotations

from collections import Counter
from datetime import date

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.llm.router import Router
from finn.network import extract as ex
from finn.network.resolve import OrgIndex, name_similarity, norm_person, resolve_org


def seed_company_orgs(conn: Connection, symbols: list[str]) -> int:
    rows = conn.execute(
        "SELECT id, nse_symbol, name, industry FROM companies WHERE nse_symbol = ANY(%s)", (symbols,)
    ).fetchall()
    for cid, sym, name, ind in rows:
        conn.execute(
            "INSERT INTO orgs (canonical_name, aliases, company_id, industry, kind) "
            "VALUES (%s, %s, %s, %s, 'company') ON CONFLICT (canonical_name) DO UPDATE SET "
            "company_id = EXCLUDED.company_id, industry = EXCLUDED.industry, "
            "aliases = (SELECT array_agg(DISTINCT a) FROM unnest(orgs.aliases || EXCLUDED.aliases) a)",
            (name, [sym], cid, ind),
        )
    conn.commit()
    return len(rows)


def targets(conn: Connection, company_ids: list[int]) -> list[tuple]:
    return conn.execute(
        """
        SELECT f.id, f.company_id, f.ts_ist, f.pdf_url, f.text_pages
        FROM filings f JOIN filing_class k ON k.filing_id = f.id
        WHERE f.company_id = ANY(%s) AND k.category = 'management_change'
          AND coalesce(k.sub_type, '') NOT IN ('re_appointment')
          AND f.text_pages IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM person_mentions m WHERE m.filing_id = f.id)
        ORDER BY f.ts_ist DESC
        """,
        (company_ids,),
    ).fetchall()


def _ym(year: int | None, end: bool = False) -> date | None:
    return None if not year or not (1950 <= year <= 2035) else date(year, 12 if end else 1, 1)


def _find_person(conn: Connection, name: str, org_id: int) -> tuple[int | None, float]:
    """Existing public figure with a similar name AND corroboration at the same org."""
    best, conf = None, 0.0
    for pid, full in conn.execute(
        "SELECT id, full_name FROM persons WHERE kind = 'public_figure' AND name_norm LIKE %s",
        (f"%{norm_person(name).split()[-1]}%",),
    ).fetchall():
        sim = name_similarity(name, full)
        same_org = conn.execute(
            "SELECT 1 FROM employments WHERE person_id = %s AND org_id = %s", (pid, org_id)
        ).fetchone()
        c = min(1.0, sim * (1.0 if same_org else 0.7))
        if c > conf:
            best, conf = pid, c
    return (best, conf) if conf >= 0.9 else (None, conf)


def extract_all(conn: Connection, router: Router, company_ids: list[int], limit: int | None = None) -> dict:
    idx = OrgIndex.load(conn)
    counts: Counter = Counter()
    for fid, cid, ts, url, pages in targets(conn, company_ids)[:limit]:
        text = ex.input_text(pages)
        try:
            res = router.call(
                "BULK",
                "extract_appointment",
                ex.PROMPT_VERSION,
                ex.SYSTEM,
                text,
                ex.Extraction,
                cache_payload={"filing": fid, "text": text},
            )
        except Exception as e:  # keep going; the card falls back to the filing link
            counts["failed"] += 1
            counts[f"err:{type(e).__name__}"] += 1
            continue
        kept, dropped = ex.verify(res.data, " ".join(pages))  # type: ignore[arg-type]
        counts["dropped_unsupported"] += len(dropped)
        company_org = conn.execute("SELECT id FROM orgs WHERE company_id = %s", (cid,)).fetchone()
        if not company_org:
            continue
        for ch in kept:
            pid, conf = _find_person(conn, ch.person_name, company_org[0])
            if pid is None:
                pid = conn.execute(
                    "INSERT INTO persons (kind, full_name, name_norm, headline, is_synthetic, source, "
                    "source_url) VALUES ('public_figure', %s, %s, %s, false, 'NSE filing', %s) RETURNING id",
                    (ch.person_name.strip(), norm_person(ch.person_name), ch.role, url),
                ).fetchone()[0]  # type: ignore[index]
                conf = 1.0
                counts["new_people"] += 1
                for j in ch.career:
                    oid = resolve_org(conn, idx, j.org)
                    conn.execute(
                        "INSERT INTO employments (person_id, org_id, title, start_ym, end_ym, source_url) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (pid, oid, j.role, _ym(j.from_year), _ym(j.to_year, end=True), url),
                    )
                    counts["employments"] += 1
                for ed in ch.education:
                    oid = resolve_org(conn, idx, ed.institution, kind="institution")
                    conn.execute(
                        "INSERT INTO educations (person_id, institution_org_id, degree, end_y) "
                        "VALUES (%s,%s,%s,%s)",
                        (pid, oid, ed.degree, ed.year),
                    )
                    counts["educations"] += 1
            # The role at the filing company itself (start on appointment, end on exit).
            eff = None
            try:
                eff = date.fromisoformat(ch.effective_date) if ch.effective_date else None
            except ValueError:
                eff = None
            if ch.event in ("appointment", "re-designation"):
                conn.execute(
                    "INSERT INTO employments (person_id, org_id, title, start_ym, end_ym, source_url) "
                    "SELECT %s, %s, %s, %s, NULL, %s WHERE NOT EXISTS (SELECT 1 FROM employments "
                    "WHERE person_id = %s AND org_id = %s AND end_ym IS NULL)",
                    (pid, company_org[0], ch.role, eff or ts.date(), url, pid, company_org[0]),
                )
            conn.execute(
                "INSERT INTO person_mentions (filing_id, person_id, role, event, effective_date, "
                "match_confidence, evidence) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    fid,
                    pid,
                    ch.role,
                    ch.event,
                    eff,
                    conf,
                    Jsonb(
                        {
                            "reason_given": ch.reason_given,
                            "years_experience": ch.years_experience,
                            "dropped": dropped,
                        }
                    ),
                ),
            )
            counts["mentions"] += 1
        conn.commit()
        counts["filings"] += 1
    return dict(counts)
