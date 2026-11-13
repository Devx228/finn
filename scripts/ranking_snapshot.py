"""Snapshot the ranking state for a before/after comparison (ranking fix, 2026-11-13).

Writes JSON: the event-category filings of the last 30 days that scored under 40 (by filing id:
category, sub_type, base, decided_by, reason, one_line, tier and rank in the 30-day brief), the
7-day and 30-day "Now" lists, and the rules-stage classifier eval.

    DATABASE_URL=... python scripts/ranking_snapshot.py out.json [--ids ids.json]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from finn import db
from finn.push import evaluate
from finn.push.brief import build_brief

ADMIN = ["unclassified", "investor_meetings", "earnings_call", "agm_egm", "postal_ballot"]
IST = ZoneInfo("Asia/Kolkata")


def main(out: str, ids_file: str | None) -> None:
    now = datetime.now(IST)
    with db.connection() as conn:
        if ids_file:
            ids = json.load(open(ids_file, encoding="utf-8"))
        else:
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT f.id FROM filings f JOIN filing_class k ON k.filing_id = f.id "
                    "WHERE f.ts_ist >= now() - interval '30 days' AND f.dup_of IS NULL AND k.base < 40 "
                    "AND k.category <> ALL(%s) AND f.company_id IN (SELECT company_id FROM holdings)",
                    (ADMIN,),
                ).fetchall()
            ]
        briefs = {w: build_brief(conn, w, now) for w in ("7d", "30d")}
        where: dict[str, tuple[str, int, int]] = {}
        for tier in ("now", "worth"):
            for i, it in enumerate(briefs["30d"][tier]):
                where[it["id"]] = (tier, i + 1, it["score"])
        rows = {}
        for fid, sym, ts, cat, st, base, by, reason, one, subj in conn.execute(
            "SELECT f.id, c.nse_symbol, f.ts_ist, k.category, k.sub_type, k.base, k.decided_by, k.reason, "
            "k.one_line, f.subject FROM filings f JOIN filing_class k ON k.filing_id = f.id "
            "JOIN companies c ON c.id = f.company_id WHERE f.id = ANY(%s)",
            (ids,),
        ).fetchall():
            t = where.get(f"f{fid}", ("buried", None, None))
            rows[fid] = {
                "symbol": sym,
                "date": ts.astimezone(IST).strftime("%d %b"),
                "category": cat,
                "sub_type": st,
                "base": base,
                "decided_by": by,
                "reason": reason,
                "one_line": one,
                "subject": (subj or "")[:140],
                "tier_30d": t[0],
                "rank_30d": t[1],
                "score_30d": t[2],
            }
        now_lists = {
            w: [{"symbol": it["symbol"], "score": it["score"], "headline": it["headline"]} for it in b["now"]]
            for w, b in briefs.items()
        }
    ev = evaluate.eval_rules(evaluate.load())
    sev = evaluate.eval_severity(evaluate.load()) if hasattr(evaluate, "eval_severity") else None
    json.dump(
        {"as_of": now.isoformat(), "ids": ids, "filings": rows, "now": now_lists, "rules_eval": ev, "severity_eval": sev},
        open(out, "w", encoding="utf-8"),
        indent=1,
        ensure_ascii=False,
        default=str,
    )
    print(f"{len(rows)} filings · now 7d {len(now_lists['7d'])} · now 30d {len(now_lists['30d'])} · "
          f"rules {ev['rules_correct']}/{ev['rules_decided']} of {ev['labelled']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--ids" else None)
