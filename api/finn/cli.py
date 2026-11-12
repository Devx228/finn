"""`finn` command line: the ingest side of the system. Phase 0 has wiring commands only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from finn import db, ingest
from finn.config import REPO_ROOT
from finn.models import Brief, BriefCounts, BriefItem

SNAPSHOT_DIR = REPO_ROOT / "web" / "public" / "snapshot"
WINDOWS = ("24h", "3d", "7d", "30d")


def placeholder_brief(window: str, as_of: datetime) -> Brief:
    """Wiring-test content for Phase 0. Clearly labelled; contains no market data at all."""
    items = [
        BriefItem(
            id=f"p0-{window}-1",
            tier="now",
            company="—",
            headline="Wiring check: this row came from Postgres via the API",
        ),
        BriefItem(
            id=f"p0-{window}-2",
            tier="worth",
            company="—",
            headline="Placeholder — real filings arrive in Phase 2",
        ),
        BriefItem(id=f"p0-{window}-3", tier="buried", company="—", headline="Placeholder buried item"),
    ]
    return Brief(
        window=window,  # type: ignore[arg-type]
        as_of=as_of,
        placeholder=True,
        counts=BriefCounts(filings=3, now=1, worth=1, buried=1),
        items=items,
    )


def cmd_migrate(_: argparse.Namespace) -> int:
    with db.connection() as conn:
        applied = db.migrate(conn)
    print(f"migrations applied: {applied or 'none (up to date)'}")
    return 0


def cmd_seed_placeholder(_: argparse.Namespace) -> int:
    now = datetime.now(UTC)
    with db.connection() as conn:
        for w in WINDOWS:
            body = placeholder_brief(w, now).model_dump(mode="json")
            conn.execute(
                "INSERT INTO views (key, body, as_of) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, "
                "as_of = EXCLUDED.as_of, updated_at = now()",
                (f"brief:{w}", Jsonb(body), now),
            )
    print(f"seeded placeholder briefs for windows {', '.join(WINDOWS)}")
    return 0


def cmd_export_snapshot(args: argparse.Namespace) -> int:
    """Export every materialised view to web/public/snapshot/<key>.json (':' -> '_')."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with db.connection() as conn:
        rows = conn.execute("SELECT key, body, as_of FROM views ORDER BY key").fetchall()
    index = {}
    for key, body, as_of in rows:
        name = key.replace(":", "_") + ".json"
        (out / name).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        index[key] = {"file": name, "as_of": as_of.isoformat()}
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"exported {len(rows)} views to {out}")
    return 0


COUNT_TABLES = (
    "companies",
    "prices",
    "filings",
    "documents",
    "fin_filings",
    "fin_facts",
    "llm_cache",
    "llm_calls",
    "ingest_runs",
)


def cmd_counts(_: argparse.Namespace) -> int:
    with db.connection() as conn:
        for t in COUNT_TABLES:
            n = (conn.execute(f"SELECT count(*) FROM {t}").fetchone() or [0])[0]  # noqa: S608 (fixed list)
            print(f"  {t:12} {n:>9,}")
        print("  per company (demo set):")
        rows = conn.execute(
            """
            SELECT c.nse_symbol, c.fin_format,
              (SELECT count(*) FROM prices p WHERE p.company_id = c.id),
              (SELECT count(*) FROM filings f WHERE f.company_id = c.id),
              (SELECT count(*) FROM filings f WHERE f.company_id = c.id AND f.text_pages IS NOT NULL),
              (SELECT count(*) FROM documents d WHERE d.company_id = c.id AND d.kind='transcript'),
              (SELECT count(*) FROM documents d WHERE d.company_id = c.id AND d.kind='annual_report'),
              (SELECT count(*) FROM fin_filings x WHERE x.company_id = c.id AND x.parse_error IS NULL)
            FROM companies c WHERE c.nse_symbol = ANY(%s) ORDER BY c.nse_symbol
            """,
            (ingest.demo_symbols(),),
        ).fetchall()
        print(
            f"    {'symbol':11} {'format':6} {'prices':>6} {'filings':>7} {'w/text':>6} "
            f"{'transcr':>7} {'ARs':>4} {'xbrl':>5}"
        )
        for r in rows:
            print(
                f"    {r[0]:11} {r[1] or 'indas':6} {r[2]:>6} {r[3]:>7} {r[4]:>6} {r[5]:>7} "
                f"{r[6]:>4} {r[7]:>5}"
            )
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    import socket

    from finn.sources.http import SourceRefused
    from finn.sources.nse import NSE

    syms = args.symbols.split(",") if args.symbols else ingest.demo_symbols()
    if not syms and args.step not in ("symbols",):
        print("no demo symbols: run scripts/pick_portfolio.py first, or pass --symbols")
        return 2
    nse = NSE()
    steps = {
        "symbols": lambda c: ingest.ingest_symbols(c, nse),
        "prices": lambda c: ingest.ingest_prices(c, syms),
        "filings": lambda c: ingest.ingest_filings(c, nse, syms, days=args.days),
        "transcripts": lambda c: ingest.ingest_transcript_history(c, nse, syms),
        "fundamentals": lambda c: ingest.ingest_fundamentals(c, nse, syms),
        "texts": lambda c: ingest.ingest_deep_read_texts(c, nse, syms, days=args.days),
    }
    order = list(steps) if args.step == "all" else [args.step]
    with db.connection() as conn:
        db.migrate(conn)
        run_id = conn.execute(
            "INSERT INTO ingest_runs (host) VALUES (%s) RETURNING id", (socket.gethostname(),)
        ).fetchone()[0]  # type: ignore[index]
        conn.commit()
        results: dict[str, object] = {}
        ok, err = True, None
        for name in order:
            t0 = datetime.now(UTC)
            try:
                results[name] = steps[name](conn)
                conn.commit()
            except SourceRefused as e:
                conn.rollback()
                ok, err = False, f"STOPPED: {e}"
                print(f"\n!! {err}\n!! Access rule: do not retry. Tell the owner.")
                break
            except Exception as e:
                conn.rollback()
                ok, err = False, f"{name}: {type(e).__name__}: {e}"
                print(f"\n!! step {name} failed: {err}")
                break
            secs = (datetime.now(UTC) - t0).total_seconds()
            print(f"  {name:13} {results[name]}  ({secs:.0f}s)")
        conn.execute(
            "UPDATE ingest_runs SET finished_at=now(), steps=%s, ok=%s, error=%s WHERE id=%s",
            (
                Jsonb(
                    {
                        **results,
                        "nse_requests": nse.http.requests_made,
                        "nse_cache_hits": nse.http.cache_hits,
                    }
                ),
                ok,
                err,
                run_id,
            ),
        )
        conn.commit()
    print(f"  NSE requests {nse.http.requests_made} · cache hits {nse.http.cache_hits}")
    if args.step == "all" and ok:
        print("\nrow counts:")
        cmd_counts(args)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    sub.add_parser("seed-placeholder").set_defaults(fn=cmd_seed_placeholder)
    ex = sub.add_parser("export-snapshot")
    ex.add_argument("--out", default=str(SNAPSHOT_DIR))
    ex.set_defaults(fn=cmd_export_snapshot)
    sub.add_parser("counts").set_defaults(fn=cmd_counts)
    ing = sub.add_parser("ingest")
    ing.add_argument(
        "step",
        choices=["symbols", "prices", "filings", "transcripts", "fundamentals", "texts", "all"],
    )
    ing.add_argument("--symbols", default="", help="comma-separated; default = demo set")
    ing.add_argument("--days", type=int, default=120)
    ing.set_defaults(fn=cmd_ingest)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
