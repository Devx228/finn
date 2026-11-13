"""Earnings-call transcripts for the pull side: pick the last N real earnings calls (not AGM or
'AI day' transcripts), download each once through the polite NSE client, store page text."""

from __future__ import annotations

import json
import re
from pathlib import Path

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.sources import pdf as pdfmod
from finn.sources.nse import NSE

NOT_EARNINGS = re.compile(r"agm|aiday|ai_day|business_?call|inv[se]{2}tor_?meet|analyst_?day", re.I)


def pick(conn: Connection, company_id: int, n: int = 4) -> list[tuple]:
    """Last n earnings calls, one per calendar quarter; within a quarter a copy we have text for
    (e.g. a manual import from the company's IR site) beats one we don't."""
    rows = conn.execute(
        "SELECT id, url, filed_at, pages IS NOT NULL, source FROM documents WHERE company_id = %s "
        "AND kind = 'transcript' ORDER BY date_trunc('quarter', filed_at) DESC, "
        "(pages IS NOT NULL) DESC, filed_at DESC",
        (company_id,),
    ).fetchall()
    out, seen_q = [], set()
    for did, url, filed, have, source in rows:
        if source == "NSE" and NOT_EARNINGS.search(url.rsplit("/", 1)[-1]):
            continue
        q = (filed.year, (filed.month - 1) // 3)  # one call per calendar quarter
        if q in seen_q:
            continue
        seen_q.add(q)
        out.append((did, url, filed, have, source))
        if len(out) == n:
            break
    return out


def ensure_text(conn: Connection, nse: NSE | None, company_id: int, n: int = 4) -> list[dict]:
    """Return [{id, url, filed_at, pages}] for the last n earnings calls, fetching any missing
    text (one request at a time, cached forever: documents never change)."""
    out = []
    for did, url, filed, have, source in pick(conn, company_id, n):
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
        out.append({"id": did, "url": url, "filed_at": filed, "pages": pages, "source": source})
    return out


def import_manual(conn: Connection, symbol: str, root: Path) -> list[str]:
    """Ingest PDFs dropped in data/manual/<SYMBOL>/ (listed in manifest.json) exactly like fetched
    transcripts: text per page into `documents`, the original URL kept for the citation link."""
    folder = root / symbol
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    cid = conn.execute("SELECT id FROM companies WHERE nse_symbol = %s", (symbol,)).fetchone()
    if cid is None:
        raise ValueError(f"unknown symbol {symbol}")
    out = []
    for c in man["calls"]:
        f = folder / c["file"]
        if not f.exists():
            out.append(f"{c['quarter']}: missing {f.name}")
            continue
        raw = f.read_bytes()
        if not raw.startswith(b"%PDF"):
            out.append(f"{c['quarter']}: {f.name} is not a PDF")
            continue
        t = pdfmod.extract(raw)
        conn.execute(
            "INSERT INTO documents (company_id, kind, period, filed_at, url, sha256, n_pages, pages, "
            "fetched_at, source) VALUES (%s, 'transcript', %s, %s::date + time '18:00' AT TIME ZONE "
            "'Asia/Kolkata', %s, %s, %s, %s, now(), %s) ON CONFLICT (url) DO UPDATE SET pages = "
            "EXCLUDED.pages, n_pages = EXCLUDED.n_pages, sha256 = EXCLUDED.sha256, "
            "filed_at = EXCLUDED.filed_at, source = EXCLUDED.source, period = EXCLUDED.period",
            (
                cid[0],
                c["quarter"],
                c["call_date"],
                c["url"],
                t.sha256,
                len(t.pages),
                Jsonb(t.pages),
                man["source"],
            ),
        )
        out.append(f"{c['quarter']}: {len(t.pages)} pages{' (scanned?)' if t.is_scanned else ''}")
    conn.commit()
    return out
