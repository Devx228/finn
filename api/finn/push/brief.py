"""Bundling, scoring, tiers and the materialised brief (spec §8.2, §8.6, §11.2).

Deterministic and explainable: every score component is stored so the UI can answer
"Why is this here?". The brief covers portfolio companies only.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.types.json import Jsonb

NOW_MIN, WORTH_MIN, NOW_CAP = 70, 40, 5
WINDOWS = {"24h": 24, "3d": 72, "7d": 168, "30d": 720}
RESULTS_FAMILY_HOURS = 36
BOILER = re.compile(
    r"^.{0,120}?\b(has )?(informed|submitted to) the exchange,? (about|regarding|that)?\s*", re.I
)
SUBTYPE_LABEL = {
    "newspaper_copy": "Newspaper copies",
    "esop": "ESOP allotments",
    "reg74_certificate": "Reg 74(5) certificates",
    "trading_window": "Trading-window closures",
    "routine": "Routine compliance",
    "recording": "Call recordings",
    "call_notice": "Call notices",
    "presentation": "Investor presentations",
    "reaffirmation": "Rating reaffirmations",
    "routine_debt": "Debt roll-overs",
    "re_appointment": "Re-appointments",
    "routine_subsidiary_infusion": "Routine subsidiary steps",
    "smp_change": "Senior-management changes",
}
CATEGORY_LABEL = {
    "results": "Results",
    "M&A": "M&A",
    "fund_raise": "Fund raise",
    "management_change": "Management change",
    "litigation": "Litigation & orders",
    "insider_trading": "Insider trading",
    "earnings_call": "Earnings calls",
    "investor_meetings": "Investor meetings",
    "credit_rating": "Credit rating",
    "dividend": "Dividend",
    "bonus_split": "Bonus / split",
    "capex": "Capex",
    "press_release": "Press releases",
    "postal_ballot": "Postal ballots",
    "agm_egm": "AGM / EGM",
    "pledging": "Pledging",
    "unclassified": "Routine paperwork",
}
RESULTS_FAMILY = {
    ("results", None),
    ("earnings_call", "call_notice"),
    ("earnings_call", "recording"),
    ("investor_meetings", "presentation"),
    ("unclassified", "newspaper_copy"),
}


def clean_subject(s: str | None) -> str:
    s = (s or "").strip().replace("&#8377;", "₹")
    s = BOILER.sub("", s, count=1).strip(" '\".")
    return (s[:1].upper() + s[1:])[:160] if s else ""


@dataclass
class Item:
    id: str
    company_id: int
    symbol: str
    name: str
    ts: datetime
    category: str
    sub_type: str | None
    base: int
    filing_ids: list[int]
    headline: str
    pdf_url: str | None
    reason: str | None
    kind: str = "filing"
    card: dict | None = None
    components: dict = field(default_factory=dict)
    score: int = 0


def portfolio(conn: Connection) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT c.nse_symbol, h.weight_pct FROM holdings h JOIN companies c ON c.id = h.company_id"
    ).fetchall()
    return {sym: {"weight_pct": float(w)} for sym, w in rows}


def load_items(conn: Connection, since: datetime) -> list[Item]:
    port = portfolio(conn)
    rows = conn.execute(
        """
        SELECT f.id, f.company_id, c.nse_symbol, c.name, f.ts_ist, k.category, k.sub_type, k.base,
               f.subject, f.pdf_url, coalesce(k.one_line, ''), k.reason
        FROM filings f JOIN companies c ON c.id = f.company_id
        JOIN filing_class k ON k.filing_id = f.id
        WHERE c.nse_symbol = ANY(%s) AND f.ts_ist >= %s AND f.dup_of IS NULL
        ORDER BY f.ts_ist
        """,
        (list(port), since),
    ).fetchall()
    items = []
    for fid, cid, sym, name, ts, cat, st, base, subj, url, one_line, reason in rows:
        items.append(
            Item(
                f"f{fid}",
                cid,
                sym,
                name,
                ts,
                cat,
                st,
                base,
                [fid],
                one_line or clean_subject(subj),
                url,
                reason,
            )
        )
    return bundle_results(items)


def bundle_results(items: list[Item]) -> list[Item]:
    """Results day produces several filings; fold the family into the results filing's item."""
    by_co: dict[int, list[Item]] = defaultdict(list)
    for it in items:
        by_co[it.company_id].append(it)
    out: list[Item] = []
    for group in by_co.values():
        anchors = [i for i in group if i.category == "results" and i.sub_type == "results_filing"]
        absorbed: set[str] = set()
        for a in anchors:
            for i in group:
                if (
                    i is a
                    or i.id in absorbed
                    or (i.category, i.sub_type) not in RESULTS_FAMILY
                    and (i.category, None) not in RESULTS_FAMILY
                ):
                    continue
                if abs((i.ts - a.ts).total_seconds()) <= RESULTS_FAMILY_HOURS * 3600:
                    a.filing_ids.append(i.filing_ids[0])
                    absorbed.add(i.id)
        out.extend(i for i in group if i.id not in absorbed)
    return out


def attach_cards(conn: Connection, items: list[Item]) -> None:
    for it in items:
        if it.category == "results" and it.sub_type == "results_filing":
            row = conn.execute(
                "SELECT card FROM results_cards WHERE company_id = %s AND period_end < %s::date "
                "AND period_end >= %s::date - 75 ORDER BY (basis = 'consolidated') DESC, period_end DESC "
                "LIMIT 1",
                (it.company_id, it.ts, it.ts),
            ).fetchone()
            if row:
                it.kind, it.card = "results", row[0]
                it.headline = f"{row[0]['period_label']} results: {row[0]['take']}"


def price_reaction(conn: Connection, company_id: int, ts: datetime) -> tuple[int, dict]:
    """Abnormal return and volume multiple on the first session at/after the filing."""
    row = conn.execute(
        """
        WITH p AS (
          SELECT date, close, volume,
                 lag(close) OVER (ORDER BY date) AS prev_close,
                 avg(volume) OVER (ORDER BY date ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg20
          FROM prices WHERE company_id = %s),
        n AS (
          SELECT date, close / lag(close) OVER (ORDER BY date) - 1 AS r
          FROM prices WHERE company_id = (SELECT id FROM companies WHERE nse_symbol = '^NSEI'))
        SELECT p.date, p.close / p.prev_close - 1, n.r, p.volume / nullif(p.avg20, 0)
        FROM p JOIN n USING (date)
        WHERE p.date >= (%s AT TIME ZONE 'Asia/Kolkata')::date + CASE
              WHEN extract(hour FROM %s AT TIME ZONE 'Asia/Kolkata') >= 15 THEN 1 ELSE 0 END
        ORDER BY p.date LIMIT 1
        """,
        (company_id, ts, ts),
    ).fetchone()
    if not row or row[1] is None or row[2] is None:
        return 0, {}
    d, r, nr, vm = row
    abn = float(r - nr)
    pts = min(10, round(abs(abn) * 100 * 2))
    if vm is not None and float(vm) >= 2:
        pts = max(pts, min(10, round(float(vm) * 3)))
    return pts, {
        "session": str(d),
        "abnormal_return_pct": round(abn * 100, 1),
        "volume_multiple": round(float(vm), 1) if vm is not None else None,
    }


def magnitude(it: Item) -> tuple[int, str | None]:
    if it.kind == "results" and it.card:
        pat = next((r for r in it.card["rows"] if r["metric"] == "pat"), None)
        yoy = pat and pat.get("yoy_pct")
        if yoy is not None:
            return min(20, round(abs(yoy) / 3)), f"PAT {yoy:+.0f}% YoY"
        return 8, "results without a year-ago comparison"
    return 0, None


def score(conn: Connection, items: list[Item], now: datetime, window_h: int) -> None:
    port = portfolio(conn)
    for it in items:
        mag, mag_why = magnitude(it)
        weight = port.get(it.symbol, {}).get("weight_pct") or 0
        pr, pr_info = price_reaction(conn, it.company_id, it.ts)
        age_h = max(0.0, (now - it.ts).total_seconds() / 3600)
        stale = round(min(10, age_h / window_h * 10))
        it.components = {
            "base": {"points": it.base, "why": it.reason},
            "magnitude": {"points": mag, "why": mag_why},
            "portfolio": {"points": min(10, round(weight * 1.2)), "why": f"{weight}% of portfolio"},
            "network": {"points": 0, "why": "network layer arrives in Phase 3"},
            "price_reaction": {"points": pr, "why": pr_info or None},
            "user_pref": {"points": 0, "why": None},
            "staleness": {"points": -stale, "why": f"{age_h:.0f} h old"},
        }
        it.score = sum(c["points"] for c in it.components.values())


def tiers(items: list[Item]) -> dict[str, list[Item]]:
    ranked = sorted(items, key=lambda i: (-i.score, i.ts))
    now = [i for i in ranked if i.score >= NOW_MIN][:NOW_CAP]
    rest = [i for i in ranked if i not in now]
    worth = [i for i in rest if i.score >= WORTH_MIN]
    buried = [i for i in rest if i.score < WORTH_MIN]
    return {"now": now, "worth": worth, "buried": buried}


def _item_json(it: Item, tier: str) -> dict:
    return {
        "id": it.id,
        "tier": tier,
        "symbol": it.symbol,
        "company": it.name,
        "ts": it.ts.isoformat(),
        "category": it.category,
        "category_label": CATEGORY_LABEL.get(it.category, it.category),
        "sub_type": it.sub_type,
        "kind": it.kind,
        "headline": it.headline,
        "score": it.score,
        "components": it.components,
        "pdf_url": it.pdf_url,
        "filing_ids": it.filing_ids,
        "bundled": len(it.filing_ids) - 1,
        "card": it.card,
    }


def build_brief(conn: Connection, window: str, now: datetime) -> dict:
    hours = WINDOWS[window]
    items = load_items(conn, now - timedelta(hours=hours))
    items = [i for i in items if i.ts <= now]
    attach_cards(conn, items)
    score(conn, items, now, hours)
    t = tiers(items)
    groups: dict[str, list[Item]] = defaultdict(list)
    for it in t["buried"]:
        groups[SUBTYPE_LABEL.get(it.sub_type or "", CATEGORY_LABEL.get(it.category, it.category))].append(it)
    n_filings = sum(len(i.filing_ids) for i in items)
    return {
        "window": window,
        "as_of": now.isoformat(),
        "placeholder": False,
        "counts": {
            "filings": n_filings,
            "now": len(t["now"]),
            "worth": len(t["worth"]),
            "buried": sum(len(i.filing_ids) for i in t["buried"]),
        },
        "now": [_item_json(i, "now") for i in t["now"]],
        "worth": [_item_json(i, "worth") for i in t["worth"]],
        "buried": [
            {"label": k, "count": len(v), "items": [_item_json(i, "buried") for i in v]}
            for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))
        ],
        "source_credit": "Filings: NSE. Prices: Yahoo Finance. Portfolio weights are synthetic.",
    }


def materialise(conn: Connection, now: datetime) -> dict[str, int]:
    out = {}
    for w in WINDOWS:
        body = build_brief(conn, w, now)
        conn.execute(
            "INSERT INTO views (key, body, as_of) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE "
            "SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
            (f"brief:{w}", Jsonb(body), now),
        )
        out[w] = body["counts"]["filings"]
    conn.commit()
    return out
