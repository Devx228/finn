"""Triggered alerts (brief: "tell me the moment something crosses a threshold").

The server materialises the inputs once — per holding, the last 90 sessions of close/volume and
the material filings — and the rule evaluation is a pure function, run identically here (tests,
replays) and in the browser (web/lib/alerts.ts), so moving a slider instantly shows which alerts
would have fired. Rules are the investor's: volume ≥ N× its 20-session average, |move| ≥ X% in a
day (absolute, and optionally relative to NIFTY), and filing categories they care about.
"""

from __future__ import annotations

from datetime import date, datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from finn.push.brief import CATEGORY_LABEL, clean_subject

DEFAULT_RULES = {
    "volume_x": 2.0,
    "move_pct": 4.0,
    "vs_nifty": False,
    "categories": ["results", "M&A", "management_change", "litigation", "fund_raise", "capex"],
    "days": 30,
}
SESSIONS = 90


def inputs(conn: Connection, now: datetime) -> dict:
    hold = conn.execute(
        "SELECT c.id, c.nse_symbol, c.name FROM holdings h JOIN companies c ON c.id = h.company_id ORDER BY 2"
    ).fetchall()
    nifty = conn.execute("SELECT id FROM companies WHERE nse_symbol = '^NSEI'").fetchone()
    ids = [h[0] for h in hold] + ([nifty[0]] if nifty else [])
    series: dict[int, list] = {i: [] for i in ids}
    for cid, d, close, vol in conn.execute(
        "SELECT company_id, date, close, volume FROM prices WHERE company_id = ANY(%s) "
        "AND date >= (SELECT max(date) FROM prices) - 140 ORDER BY company_id, date",
        (ids,),
    ).fetchall():
        series[cid].append([str(d), float(close) if close is not None else None, int(vol or 0)])
    filings = conn.execute(
        "SELECT f.id, c.nse_symbol, f.ts_ist, k.category, "
        "coalesce(nullif(k.one_line, ''), f.subject), f.pdf_url "
        "FROM filings f JOIN filing_class k ON k.filing_id = f.id JOIN companies c ON c.id = f.company_id "
        "JOIN holdings h ON h.company_id = c.id WHERE f.ts_ist >= %s::date - 90 AND f.dup_of IS NULL "
        "AND coalesce(k.base, 0) >= 40 ORDER BY f.ts_ist DESC",
        (now.date(),),
    ).fetchall()
    return {
        "as_of": now.isoformat(),
        "defaults": DEFAULT_RULES,
        "category_labels": CATEGORY_LABEL,
        "nifty": series.get(nifty[0], [])[-SESSIONS:] if nifty else [],
        "companies": [
            {"symbol": sym, "name": name, "bars": series[cid][-SESSIONS:]} for cid, sym, name in hold
        ],
        "filings": [
            {
                "id": fid,
                "symbol": sym,
                "ts": ts.isoformat(),
                "category": cat,
                "headline": clean_subject(subj)[:160],
                "url": url,
            }
            for fid, sym, ts, cat, subj, url in filings
        ],
        "credit": "Prices: Yahoo Finance (end of day). Filings: NSE.",
    }


def evaluate(data: dict, rules: dict) -> list[dict]:
    """Pure: the same logic as web/lib/alerts.ts. Returns fired alerts, newest first."""
    out: list[dict] = []
    nifty = {d: c for d, c, _ in data["nifty"]}
    nd = sorted(nifty)
    nret = {nd[i]: nifty[nd[i]] / nifty[nd[i - 1]] - 1 for i in range(1, len(nd)) if nifty[nd[i - 1]]}
    last_day = max((b[0] for c in data["companies"] for b in c["bars"]), default=None)
    if last_day is None:
        return out
    cutoff = date.fromordinal(date.fromisoformat(last_day).toordinal() - rules["days"]).isoformat()
    for c in data["companies"]:
        bars = c["bars"]
        for i in range(20, len(bars)):
            d, close, vol = bars[i]
            prev = bars[i - 1][1]
            if d < cutoff or close is None or not prev:
                continue
            avg = sum(b[2] for b in bars[i - 20 : i]) / 20
            vx = vol / avg if avg else 0
            r = (close / prev - 1) * 100
            rel = r - nret.get(d, 0) * 100 if rules.get("vs_nifty") else r
            if vx >= rules["volume_x"]:
                out.append(
                    {
                        "kind": "volume",
                        "symbol": c["symbol"],
                        "date": d,
                        "value": round(vx, 1),
                        "move_pct": round(r, 1),
                        "text": f"Volume {vx:.1f}× its 20-day average ({r:+.1f}%)",
                    }
                )
            if abs(rel) >= rules["move_pct"]:
                txt = f"{'Up' if r > 0 else 'Down'} {abs(r):.1f}% in a day" + (
                    f" ({rel:+.1f}% vs NIFTY)" if rules.get("vs_nifty") else ""
                )
                out.append(
                    {
                        "kind": "price",
                        "symbol": c["symbol"],
                        "date": d,
                        "value": round(r, 1),
                        "move_pct": round(r, 1),
                        "text": txt,
                    }
                )
    cats = set(rules["categories"])
    for f in data["filings"]:
        if f["category"] in cats and f["ts"][:10] >= cutoff:
            out.append(
                {
                    "kind": "filing",
                    "symbol": f["symbol"],
                    "date": f["ts"][:10],
                    "value": None,
                    "text": f"{data['category_labels'].get(f['category'], f['category'])}: {f['headline']}",
                    "url": f["url"],
                }
            )
    return sorted(out, key=lambda a: (a["date"], a["kind"]), reverse=True)


def materialise(conn: Connection, now: datetime) -> dict[str, int]:
    body = inputs(conn, now)
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES ('alerts:inputs', %s, %s) ON CONFLICT (key) DO UPDATE "
        "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
        (Jsonb(body), now),
    )
    conn.commit()
    return {
        "companies": len(body["companies"]),
        "filings": len(body["filings"]),
        "fired_default": len(evaluate(body, DEFAULT_RULES)),
    }
