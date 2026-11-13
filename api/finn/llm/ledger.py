"""Cost ledger view (spec §6.3): what the system spent to produce what the user sees.

Materialised from `llm_calls` (every model call, hit or miss) and `filing_class` (how each filing
was decided), so the screen is a read of one view. Actual cost on free tiers and a local model is
zero; the paid-list-price equivalent is shown only for calls whose price is verified in
`llm/store.py` — everything else is counted and labelled "price not verified", never estimated.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb


def summary(conn: Connection) -> dict:
    by_model = [
        {
            "provider": p,
            "model": m,
            "calls": int(n),
            "cache_hits": int(h),
            "failed": int(f),
            "input_tokens": int(ti or 0),
            "output_tokens": int(to or 0),
            "avg_latency_ms": int(lat) if lat is not None else None,
            "list_price_usd": float(usd) if usd is not None else None,
            "priced_calls": int(pc),
        }
        for p, m, n, h, f, ti, to, lat, usd, pc in conn.execute(
            "SELECT provider, model, count(*), count(*) FILTER (WHERE cache_hit), "
            "count(*) FILTER (WHERE NOT ok), sum(input_tokens), sum(output_tokens), "
            "avg(latency_ms) FILTER (WHERE NOT cache_hit AND ok), sum(list_price_usd), "
            "count(list_price_usd) FROM llm_calls GROUP BY 1, 2 ORDER BY 3 DESC"
        ).fetchall()
    ]
    by_purpose = [
        {"purpose": p, "calls": int(n), "cache_hits": int(h)}
        for p, n, h in conn.execute(
            "SELECT purpose, count(*), count(*) FILTER (WHERE cache_hit) FROM llm_calls "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    ]
    decided: dict[str, int] = dict(
        conn.execute(
            "SELECT coalesce(decided_by, 'unknown'), count(*) FROM filing_class GROUP BY 1"
        ).fetchall()
    )
    filings = int(conn.execute("SELECT count(*) FROM filings WHERE dup_of IS NULL").fetchone()[0])  # type: ignore[index]
    docs: dict[str, int] = dict(
        conn.execute("SELECT source, count(*) FROM documents WHERE pages IS NOT NULL GROUP BY 1").fetchall()
    )
    calls = sum(x["calls"] for x in by_model)
    hits = sum(x["cache_hits"] for x in by_model)
    return {
        "as_of": datetime.now().astimezone().isoformat(),
        "totals": {
            "model_calls": calls,
            "cache_hits": hits,
            "cache_hit_rate": round(hits / calls * 100, 1) if calls else None,
            "input_tokens": sum(x["input_tokens"] for x in by_model),
            "output_tokens": sum(x["output_tokens"] for x in by_model),
            "actual_cost_inr": 0,
            "list_price_usd": round(sum(x["list_price_usd"] or 0 for x in by_model), 4),
            "unpriced_calls": sum(x["calls"] - x["priced_calls"] for x in by_model),
        },
        "filings": {
            "total": filings,
            "by_rules": int(decided.get("rules", 0)),
            "by_model": int(decided.get("llm", 0)),
        },
        "documents_read": {str(k): int(v) for k, v in docs.items()},
        "by_model": by_model,
        "by_purpose": by_purpose,
        "note": (
            "Free tiers (Gemini, Groq) and a local model (Ollama): actual cost is zero. List-price "
            "equivalents appear only for models whose paid price is verified; others are counted, "
            "not estimated."
        ),
    }


def materialise(conn: Connection) -> dict:
    body = summary(conn)
    conn.execute(
        "INSERT INTO views (key, body, as_of) VALUES ('cost:summary', %s, now()) ON CONFLICT (key) "
        "DO UPDATE SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
        (Jsonb(body),),
    )
    conn.commit()
    return body["totals"]
