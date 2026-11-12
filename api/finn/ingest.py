"""Ingest steps (laptop / scheduled job only; never on a user request).

Each step is idempotent and returns a count dict. All NSE traffic goes through one polite
client; a refusal raises SourceRefused and the run stops.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.config import REPO_ROOT
from finn.fin.xbrl import parse_xbrl
from finn.sources import pdf as pdfmod
from finn.sources import prices as pricemod
from finn.sources.base import Announcement, ResultsFiling
from finn.sources.nse import NSE, is_transcript

DATA = REPO_ROOT / "data"
QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}


# -- demo universe -----------------------------------------------------------
def demo_symbols() -> list[str]:
    syms: list[str] = []
    for name in ("portfolio.json", "research_set.json"):
        p = DATA / name
        if p.exists():
            for h in json.loads(p.read_text(encoding="utf-8"))["companies"]:
                if h["symbol"] not in syms:
                    syms.append(h["symbol"])
    return syms


def company_ids(conn: Connection, symbols: list[str]) -> dict[str, int]:
    rows = conn.execute(
        "SELECT nse_symbol, id FROM companies WHERE nse_symbol = ANY(%s)", (symbols,)
    ).fetchall()
    found = dict(rows)
    missing = [s for s in symbols if s not in found]
    if missing:
        raise ValueError(f"not in NSE symbol master (run `finn ingest symbols`): {missing}")
    return found


# -- symbols -----------------------------------------------------------------
def ingest_symbols(conn: Connection, nse: NSE) -> dict[str, int]:
    syms = nse.symbols()
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO companies (nse_symbol, isin, name, series, listed_on) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (nse_symbol) DO UPDATE SET "
            "isin = EXCLUDED.isin, name = EXCLUDED.name, series = EXCLUDED.series, "
            "listed_on = EXCLUDED.listed_on, updated_at = now()",
            [(s.symbol, s.isin, s.name, s.series, s.listed_on) for s in syms],
        )
    conn.execute(
        "INSERT INTO companies (nse_symbol, kind, name) VALUES (%s, 'index', 'NIFTY 50') "
        "ON CONFLICT (nse_symbol) DO NOTHING",
        (pricemod.NIFTY,),
    )
    return {"symbols": len(syms)}


# -- prices ------------------------------------------------------------------
def ingest_prices(conn: Connection, symbols: list[str], period: str = "1y") -> dict[str, int]:
    ids = company_ids(conn, symbols + [pricemod.NIFTY])
    by_ticker = {pricemod.yahoo_ticker(s): ids[s] for s in ids}
    bars = pricemod.download(list(by_ticker), period=period)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO prices (company_id, date, open, high, low, close, adj_close, volume) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (company_id, date) DO UPDATE SET "
            "open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close, "
            "adj_close=EXCLUDED.adj_close, volume=EXCLUDED.volume",
            [
                (by_ticker[b.ticker], b.date, b.open, b.high, b.low, b.close, b.adj_close, b.volume)
                for b in bars
            ],
        )
    got = {b.ticker for b in bars}
    return {
        "price_rows": len(bars),
        "tickers": len(got),
        "tickers_missing": len(set(by_ticker) - got),
    }


# -- filings -----------------------------------------------------------------
def upsert_announcements(conn: Connection, company_id: int, anns: list[Announcement]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO filings (company_id, exchange, exch_id, ts_ist, exch_category, subject, "
            "pdf_url, pdf_size_label, raw) VALUES (%s,'NSE',%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (exchange, exch_id) DO UPDATE SET exch_category = EXCLUDED.exch_category, "
            "subject = EXCLUDED.subject, pdf_url = EXCLUDED.pdf_url",
            [
                (
                    company_id,
                    a.exch_id,
                    a.ts,
                    a.category,
                    a.subject,
                    a.pdf_url,
                    a.pdf_size_label,
                    Jsonb(a.raw),
                )
                for a in anns
            ],
        )
    return len(anns)


def ingest_filings(
    conn: Connection, nse: NSE, symbols: list[str], days: int = 120, end: date | None = None
) -> dict[str, int]:
    end = end or date.today()
    ids = company_ids(conn, symbols)
    n = tr = 0
    for s in symbols:
        anns = nse.announcements(s, end - timedelta(days=days), end)
        n += upsert_announcements(conn, ids[s], anns)
        ind = next((a.industry for a in anns if a.industry), None)
        if ind:
            conn.execute("UPDATE companies SET industry = %s WHERE id = %s", (ind, ids[s]))
        tr += _record_transcripts(conn, ids[s], anns)
        conn.commit()
    return {"filings_upserted": n, "transcript_links": tr}


def _record_transcripts(conn: Connection, company_id: int, anns: list[Announcement]) -> int:
    rows = [a for a in anns if is_transcript(a)]
    for a in rows:
        conn.execute(
            "INSERT INTO documents (company_id, kind, period, filed_at, url, size_label, filing_id) "
            "VALUES (%s, 'transcript', NULL, %s, %s, %s, "
            " (SELECT id FROM filings WHERE exchange='NSE' AND exch_id=%s)) "
            "ON CONFLICT (url) DO NOTHING",
            (company_id, a.ts, a.pdf_url, a.pdf_size_label, a.exch_id),
        )
    return len(rows)


def ingest_transcript_history(
    conn: Connection, nse: NSE, symbols: list[str], years: int = 2
) -> dict[str, int]:
    """Transcript links over ~8 quarters (one listing request per company)."""
    end = date.today()
    ids = company_ids(conn, symbols)
    total = 0
    for s in symbols:
        anns = nse.announcements(s, end - timedelta(days=365 * years + 30), end)
        total += _record_transcripts(conn, ids[s], anns)
        conn.commit()
    return {"transcript_links": total}


def fetch_filing_text(conn: Connection, nse: NSE, filing_id: int) -> bool:
    """Download a filing PDF once and store its page text. Returns False if none."""
    row = conn.execute(
        "SELECT pdf_url, text_fetched_at FROM filings WHERE id = %s", (filing_id,)
    ).fetchone()
    if row is None or not row[0] or row[1] is not None:
        return row is not None and row[1] is not None
    if not row[0].lower().endswith(".pdf"):
        return False
    t = pdfmod.extract(nse.fetch(row[0]))
    conn.execute(
        "UPDATE filings SET pdf_sha256=%s, n_pages=%s, text_pages=%s, is_scanned=%s, "
        "text_fetched_at=now() WHERE id=%s",
        (t.sha256, t.n_pages, Jsonb(t.pages), t.is_scanned, filing_id),
    )
    conn.commit()
    return True


def ingest_deep_read_texts(
    conn: Connection, nse: NSE, symbols: list[str], days: int = 120
) -> dict[str, int]:
    """Fetch PDF text only for filings a later stage must read: management changes (bio and
    role are only in the PDF) and M&A / capex / litigation events. Everything else stays
    metadata-only until the classifier asks for it (minimal footprint)."""
    from finn.push.tagger import tag

    ids = company_ids(conn, symbols)
    rows = conn.execute(
        "SELECT id, exch_id, ts_ist, exch_category, subject, pdf_url FROM filings "
        "WHERE company_id = ANY(%s) AND ts_ist >= now() - make_interval(days => %s) "
        "AND text_fetched_at IS NULL AND pdf_url ILIKE '%%.pdf'",
        (list(ids.values()), days),
    ).fetchall()
    n = 0
    for fid, exch_id, ts, cat, subj, url in rows:
        a = Announcement(exch_id, "", ts, cat, subj, url, None, None, {})
        if tag(a) in ("management_change", "M&A", "capex", "litigation"):
            n += fetch_filing_text(conn, nse, fid)
    return {"texts_fetched": n}


# -- fundamentals ------------------------------------------------------------
def select_results(
    filings: list[ResultsFiling],
    today: date | None = None,
    recent_quarters: int = 16,
    years: int = 10,
) -> list[ResultsFiling]:
    """Choose the minimum set of XBRL filings to fetch.

    Periods needed: every quarter in the last `recent_quarters` (QoQ / YoY / guidance checks)
    and every half-year end (Sep, Mar) in the last `years` (balance sheet, cash flow, full
    year). Per period: consolidated if it exists, else standalone (labelled by basis, never
    spliced silently). Among revisions of the same period and basis, the latest filing wins.
    """
    today = today or date.today()
    q_cut = today - timedelta(days=int(recent_quarters * 91.5))
    y_cut = today - timedelta(days=365 * years + 31)
    best: dict[tuple[date, str], ResultsFiling] = {}
    for f in filings:
        if (f.period_end.month, f.period_end.day) not in QUARTER_ENDS:
            continue
        k = (f.period_end, f.basis)
        cur = best.get(k)
        if cur is None or (f.filed_at or datetime.min.replace(tzinfo=UTC)) > (
            cur.filed_at or datetime.min.replace(tzinfo=UTC)
        ):
            best[k] = f
    chosen = []
    for end in sorted({e for e, _ in best}):
        half_year = end.month in (3, 9)
        if not (end >= q_cut or (half_year and end >= y_cut)):
            continue
        f = best.get((end, "consolidated")) or best.get((end, "standalone"))
        if f:
            chosen.append(f)
    return chosen


def ingest_fundamentals(conn: Connection, nse: NSE, symbols: list[str]) -> dict[str, int]:
    ids = company_ids(conn, symbols)
    counts: dict[str, int] = defaultdict(int)
    for s in symbols:
        cid = ids[s]
        for ar in nse.annual_reports(s):
            conn.execute(
                "INSERT INTO documents (company_id, kind, period, filed_at, url, size_label) "
                "VALUES (%s, 'annual_report', %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING",
                (cid, ar.fy_label, ar.filed_at, ar.url, ar.size_label),
            )
            counts["annual_report_links"] += 1
        listing = nse.results_filings(s)
        fmt_flags = {f.fmt for f in listing if f.fmt}
        for f in select_results(listing):
            done = conn.execute(
                "SELECT parsed_at FROM fin_filings WHERE xbrl_url = %s", (f.xbrl_url,)
            ).fetchone()
            if done and done[0]:
                counts["xbrl_already_parsed"] += 1
                continue
            counts["xbrl_parsed"] += _ingest_one_xbrl(conn, nse, cid, f)
        fmt = "bank" if "B" in fmt_flags else ("nbfc" if "F" in fmt_flags else None)
        if fmt:
            conn.execute(
                "UPDATE companies SET fin_format=%s, is_financial=true WHERE id=%s", (fmt, cid)
            )
        conn.commit()
    return dict(counts)


def _ingest_one_xbrl(conn: Connection, nse: NSE, company_id: int, f: ResultsFiling) -> int:
    content = nse.fetch(f.xbrl_url)
    try:
        p = parse_xbrl(content)
        err = None
    except Exception as e:  # keep the row so we never refetch; record why
        p, err = None, f"{type(e).__name__}: {e}"[:300]
    row = conn.execute(
        "INSERT INTO fin_filings (company_id, source, basis, fmt, period_start, period_end, "
        "audited, filed_at, xbrl_url, rounding, n_facts, parsed_at, parse_error) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s) "
        "ON CONFLICT (xbrl_url) DO UPDATE SET parsed_at = now(), n_facts = EXCLUDED.n_facts, "
        "parse_error = EXCLUDED.parse_error, fmt = EXCLUDED.fmt RETURNING id",
        (
            company_id,
            f.source,
            f.basis,
            f.fmt or (p.fmt if p else None),
            f.period_start,
            f.period_end,
            f.audited,
            f.filed_at,
            f.xbrl_url,
            (p.meta.get("LevelOfRoundingUsedInFinancialStatements") if p else None),
            (len(p.facts) if p else 0),
            err,
        ),
    ).fetchone()
    assert row is not None
    if p is None:
        return 0
    if p.fmt in ("bank", "nbfc") and f.fmt is None:
        conn.execute(
            "UPDATE companies SET fin_format=%s, is_financial=true WHERE id=%s", (p.fmt, company_id)
        )
    conn.execute("DELETE FROM fin_facts WHERE fin_filing_id = %s", (row[0],))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO fin_facts (fin_filing_id, concept, dims, period_start, period_end, "
            "value, unit) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            [
                (row[0], x.concept, x.dims, x.period_start, x.period_end, Decimal(x.value), x.unit)
                for x in p.facts
            ],
        )
    return 1


# -- coverage (what a report can be based on) --------------------------------
def coverage(conn: Connection, company_id: int) -> dict:
    q = conn.execute(
        """
        SELECT basis, count(*) AS n, min(period_end), max(period_end)
        FROM fin_filings WHERE company_id = %s AND parse_error IS NULL GROUP BY basis
        """,
        (company_id,),
    ).fetchall()
    stmt = conn.execute(
        """
        SELECT count(DISTINCT ff.period_end) FILTER (WHERE x.concept = 'Assets'),
               count(DISTINCT ff.period_end) FILTER (
                   WHERE x.concept = 'CashFlowsFromUsedInOperatingActivities'
                     AND date_part('month', ff.period_end) = 3)
        FROM fin_filings ff JOIN fin_facts x ON x.fin_filing_id = ff.id
        WHERE ff.company_id = %s AND x.dims = ''
          AND x.concept IN ('Assets', 'CashFlowsFromUsedInOperatingActivities')
        """,
        (company_id,),
    ).fetchone()
    docs = dict(
        conn.execute(
            "SELECT kind, count(*) FROM documents WHERE company_id = %s GROUP BY kind",
            (company_id,),
        ).fetchall()
    )
    assert stmt is not None
    return {
        "results_filings": {b: {"n": n, "from": str(a), "to": str(z)} for b, n, a, z in q},
        "balance_sheets": stmt[0],
        "annual_cash_flows": stmt[1],
        "annual_reports": docs.get("annual_report", 0),
        "transcripts": docs.get("transcript", 0),
    }
