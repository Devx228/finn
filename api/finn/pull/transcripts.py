"""Earnings-call transcripts for the pull side: pick the last N real earnings calls (not AGM or
'AI day' transcripts), download each once through the polite NSE client, store page text."""

from __future__ import annotations

import re

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.sources import pdf as pdfmod
from finn.sources.nse import NSE

NOT_EARNINGS = re.compile(r"agm|aiday|ai_day|business_?call|inv[se]{2}tor_?meet|analyst_?day", re.I)


def pick(conn: Connection, company_id: int, n: int = 4) -> list[tuple]:
    rows = conn.execute(
        "SELECT id, url, filed_at, pages IS NOT NULL FROM documents WHERE company_id = %s "
        "AND kind = 'transcript' ORDER BY filed_at DESC",
        (company_id,),
    ).fetchall()
    out, seen_q = [], set()
    for did, url, filed, have in rows:
        if NOT_EARNINGS.search(url.rsplit("/", 1)[-1]):
            continue
        q = (filed.year, (filed.month - 1) // 3)  # one call per calendar quarter
        if q in seen_q:
            continue
        seen_q.add(q)
        out.append((did, url, filed, have))
        if len(out) == n:
            break
    return out


def ensure_text(conn: Connection, nse: NSE | None, company_id: int, n: int = 4) -> list[dict]:
    """Return [{id, url, filed_at, pages}] for the last n earnings calls, fetching any missing
    text (one request at a time, cached forever: documents never change)."""
    out = []
    for did, url, filed, have in pick(conn, company_id, n):
        if not have:
            if nse is None:
                continue
            t = pdfmod.extract(nse.fetch(url))
            conn.execute(
                "UPDATE documents SET pages = %s, n_pages = %s, sha256 = %s, fetched_at = now() "
                "WHERE id = %s",
                (Jsonb(t.pages), t.n_pages, t.sha256, did),
            )
            conn.commit()
        pages = conn.execute("SELECT pages FROM documents WHERE id = %s", (did,)).fetchone()[0]  # type: ignore[index]
        out.append({"id": did, "url": url, "filed_at": filed, "pages": pages})
    return out
