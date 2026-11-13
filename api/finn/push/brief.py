"""Bundling, scoring, tiers and the materialised brief (spec §8.2, §8.6, §11.2).

Deterministic and explainable: every score component is stored so the UI can answer
"Why is this here?". The brief covers portfolio companies only.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.types.json import Jsonb

IST = ZoneInfo("Asia/Kolkata")
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
    "pending": "Not yet classified",
    "esg": "ESG ratings",
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
    network: dict | None = None
    components: dict = field(default_factory=dict)
    score: int = 0
    vacant: bool = False  # an event filing with nothing useful to say: always buried


def portfolio(conn: Connection) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT c.nse_symbol, h.weight_pct FROM holdings h JOIN companies c ON c.id = h.company_id"
    ).fetchall()
    return {sym: {"weight_pct": float(w)} for sym, w in rows}


def load_items(conn: Connection, since: datetime) -> list[Item]:
    port = portfolio(conn)
    rows = conn.execute(
        """
        SELECT f.id, f.company_id, c.nse_symbol, c.name, f.ts_ist, coalesce(k.category, 'unclassified'),
               CASE WHEN k.filing_id IS NULL THEN 'pending' ELSE k.sub_type END, coalesce(k.base, 0),
               f.subject, f.pdf_url, coalesce(k.one_line, ''), coalesce(k.reason, 'not yet classified'),
               f.exch_category
        FROM filings f JOIN companies c ON c.id = f.company_id
        LEFT JOIN filing_class k ON k.filing_id = f.id
        WHERE c.nse_symbol = ANY(%s) AND f.ts_ist >= %s AND f.dup_of IS NULL
        ORDER BY f.ts_ist
        """,
        (list(port), since),
    ).fetchall()
    items = []
    from finn.push import severity as sv

    for fid, cid, sym, name, ts, cat, st, base, subj, url, one_line, reason, exch in rows:
        # the headline is the fact from the filing; an event filing whose only "summary" is the
        # exchange's label or "press release on <date>" has nothing to say and is buried
        if sv.says_nothing(one_line, exch):
            one_line = ""
        vacant = (
            cat in sv.EVENT
            and (st or "") not in sv.ROUTINE_SUBTYPES
            and not one_line
            and sv.says_nothing(clean_subject(subj), exch)
        )
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
                vacant=vacant,
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
    want = [i for i in items if i.category == "results" and i.sub_type == "results_filing"]
    if not want:
        return
    rows = conn.execute(
        "SELECT company_id, period_end, basis, card FROM results_cards WHERE company_id = ANY(%s)",
        (sorted({i.company_id for i in want}),),
    ).fetchall()
    for it in want:
        filed = it.ts.astimezone(IST).date()
        cands = [r for r in rows if r[0] == it.company_id and filed - timedelta(days=75) <= r[1] < filed]
        if not cands:
            continue
        best = max(cands, key=lambda r: (r[1], r[2] == "consolidated"))
        it.kind, it.card = "results", best[3]
        it.headline = f"{best[3]['period_label']} results: {best[3]['take']}"


class PriceBook:
    """Daily bars for the brief's companies and NIFTY, loaded in one query (a replay builds a
    brief live, so per-item queries are too slow)."""

    def __init__(self, conn: Connection, company_ids: list[int], since: datetime) -> None:
        rows = conn.execute(
            "SELECT p.company_id, p.date, p.close, p.volume FROM prices p "
            "WHERE (p.company_id = ANY(%s) OR p.company_id = "
            "(SELECT id FROM companies WHERE nse_symbol = '^NSEI')) "
            "AND p.date >= %s::date - 45 ORDER BY p.company_id, p.date",
            (company_ids, since),
        ).fetchall()
        nifty = conn.execute("SELECT id FROM companies WHERE nse_symbol = '^NSEI'").fetchone()
        self.nifty_id = nifty[0] if nifty else None
        self.bars: dict[int, list[tuple]] = defaultdict(list)
        for cid, d, close, vol in rows:
            self.bars[cid].append((d, close, vol))

    def session_after(self, cid: int, ts: datetime, now: datetime) -> tuple | None:
        """(date, return, volume multiple) for the first session that could react to a filing at
        `ts` (same day if before 3 pm IST, else next day), never later than `now`."""
        local = ts.astimezone(IST)
        first = local.date() + timedelta(days=1 if local.hour >= 15 else 0)
        bars = self.bars.get(cid, [])
        for i, (d, close, vol) in enumerate(bars):
            if d < first:
                continue
            if d > now.astimezone(IST).date() or i == 0 or close is None or bars[i - 1][1] is None:
                return None
            prior = [b[2] for b in bars[max(0, i - 20) : i] if b[2]]
            vm = (vol / (sum(prior) / len(prior))) if prior and vol else None
            return d, float(close / bars[i - 1][1] - 1), vm
        return None


def price_reaction(book: PriceBook, company_id: int, ts: datetime, now: datetime) -> tuple[int, dict]:
    """Abnormal return (vs NIFTY) and volume multiple on the first session after the filing."""
    s = book.session_after(company_id, ts, now)
    n = book.session_after(book.nifty_id, ts, now) if book.nifty_id else None
    if s is None or n is None or s[0] != n[0]:
        return 0, {}
    d, r, vm = s
    abn = r - n[1]
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


def attach_network(conn: Connection, items: list[Item]) -> None:
    """Who can help / who is this person — from the investor's network (spec §9)."""
    if not items:
        return
    try:
        from finn.network.service import Net

        net = Net(conn)
    except Exception:  # network tables empty or missing: the brief still works without it
        conn.rollback()
        return
    for it in items:
        it.network = net.for_item(it.symbol, it.category, it.filing_ids, it.name)


def score(conn: Connection, items: list[Item], now: datetime, window_h: int) -> None:
    port = portfolio(conn)
    since = min((i.ts for i in items), default=now)
    book = PriceBook(conn, sorted({i.company_id for i in items}), since)
    for it in items:
        mag, mag_why = magnitude(it)
        weight = port.get(it.symbol, {}).get("weight_pct") or 0
        pr, pr_info = price_reaction(book, it.company_id, it.ts, now)
        age_h = max(0.0, (now - it.ts).total_seconds() / 3600)
        stale = round(min(10, age_h / window_h * 10))
        it.components = {
            "base": {"points": it.base, "why": it.reason},
            "magnitude": {"points": mag, "why": mag_why},
            "portfolio": {"points": min(10, round(weight * 1.2)), "why": f"{weight}% of portfolio"},
            "network": _network_component(it),
            "price_reaction": {"points": pr, "why": pr_info or None},
            "user_pref": {"points": 0, "why": None},
            "staleness": {"points": -stale, "why": f"{age_h:.0f} h old"},
        }
        it.score = sum(c["points"] for c in it.components.values())


def _network_component(it: Item) -> dict:
    n = it.network
    if not n or not n.get("points"):
        return {"points": 0, "why": "no one in your network is close to this"}
    if n["people"] and n["people"][0]["you"]:
        why = n["people"][0]["you"][0]
    elif n["people"] and n["people"][0]["paths"]:
        p = n["people"][0]["paths"][0]
        why = f"you can reach {n['people'][0]['name']} through {p['via']['name']}"
    else:
        why = f"{n['call'][0]['name']} can give context"
    return {"points": n["points"], "why": why}


def tiers(items: list[Item]) -> dict[str, list[Item]]:
    ranked = sorted(items, key=lambda i: (-i.score, i.ts))
    now = [i for i in ranked if i.score >= NOW_MIN and not i.vacant][:NOW_CAP]
    rest = [i for i in ranked if i not in now]
    worth = [i for i in rest if i.score >= WORTH_MIN and not i.vacant]
    buried = [i for i in rest if i.score < WORTH_MIN or i.vacant]
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
        "network": it.network,
    }


def build_brief(conn: Connection, window: str, now: datetime) -> dict:
    hours = WINDOWS[window]
    items = load_items(conn, now - timedelta(hours=hours))
    items = [i for i in items if i.ts <= now]
    attach_cards(conn, items)
    attach_network(conn, items)
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
