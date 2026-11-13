"""Fetch the latest annual report for the ledger companies (owner-approved, 2026-11-13).

Rules: NSE from the laptop only on the phone hotspot. The sign is that Neon's Postgres port is
reachable directly (campus Wi-Fi blocks it); if it isn't, nothing is fetched. One request at a
time through the polite client (>= 1.2 s apart, cached forever, permanent stop on any refusal).
The PDF itself stays in the local cache (never re-hosted); its page text goes to `documents.pages`
and the page links back to NSE.

    python scripts/fetch_annual_reports.py CREDITACC,KAYNES,...
"""

from __future__ import annotations

import sys

import psycopg
from psycopg.types.json import Jsonb

from finn.config import get_settings
from finn.sources import pdf as pdfmod
from finn.sources.http import SourceRefused
from finn.sources.nse import NSE


def main(symbols: list[str]) -> int:
    url = get_settings().database_url
    if "neon.tech" not in url:
        print("refused: DATABASE_URL is not the Neon host; this check needs the real database")
        return 2
    try:
        psycopg.connect(url, connect_timeout=25).close()
    except Exception as e:
        print(f"STOP: Neon's Postgres port isn't reachable ({type(e).__name__}): not on the hotspot. Nothing fetched.")
        return 2
    nse = NSE()
    with psycopg.connect(url) as conn:
        for sym in symbols:
            row = conn.execute(
                "SELECT d.id, d.period, d.url, d.size_label, d.pages IS NOT NULL FROM documents d "
                "JOIN companies c ON c.id = d.company_id WHERE c.nse_symbol = %s AND d.kind = 'annual_report' "
                "ORDER BY d.filed_at DESC NULLS LAST LIMIT 1",
                (sym,),
            ).fetchone()
            if row is None:
                print(f"  {sym:<11} no annual report link on record")
                continue
            did, period, link, size, have = row
            if have:
                print(f"  {sym:<11} {period} already read")
                continue
            try:
                t = pdfmod.extract(nse.fetch(link))
            except SourceRefused as e:
                print(f"!! STOPPED: {e}. Access rule: do not retry; tell the owner.")
                return 1
            conn.execute(
                "UPDATE documents SET pages = %s, n_pages = %s, sha256 = %s, fetched_at = now() WHERE id = %s",
                (Jsonb(t.pages), t.n_pages, t.sha256, did),
            )
            conn.commit()
            print(f"  {sym:<11} {period} {size}: {t.n_pages} pages")
    print(f"  NSE requests {nse.http.requests_made} · cache hits {nse.http.cache_hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main([s.strip().upper() for s in sys.argv[1].split(",") if s.strip()]))
