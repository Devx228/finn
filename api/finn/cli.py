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
from finn.models import Brief, BriefCounts, BriefRow, Tier

SNAPSHOT_DIR = REPO_ROOT / "web" / "public" / "snapshot"
WINDOWS = ("24h", "3d", "7d", "30d")


def placeholder_brief(window: str, as_of: datetime) -> Brief:
    """Wiring-test content (Phase 0, still used by tests). Contains no market data at all."""

    def row(i: int, tier: Tier, headline: str) -> BriefRow:
        return BriefRow(
            id=f"p0-{window}-{i}",
            tier=tier,
            symbol="—",
            company="—",
            ts=as_of,  # type: ignore[arg-type]
            category="unclassified",
            category_label="Placeholder",
            kind="filing",
            headline=headline,
            score=0,
            components={},
            filing_ids=[],
        )

    return Brief(
        window=window,  # type: ignore[arg-type]
        as_of=as_of,
        placeholder=True,
        counts=BriefCounts(filings=3, now=1, worth=1, buried=1),
        now=[row(1, "now", "Wiring check: this row came from Postgres via the API")],
        worth=[row(2, "worth", "Placeholder")],
        buried=[],
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
        "holdings": lambda c: ingest.ingest_holdings(c),
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


def cmd_push(args: argparse.Namespace) -> int:
    """Push pipeline: rules → thin-subject texts → model → results cards → materialise briefs."""
    from zoneinfo import ZoneInfo

    from finn.llm.router import LLMUnavailable, Router
    from finn.llm.store import LLMStore
    from finn.network import service as network_views
    from finn.push import alerts, brief, pipeline
    from finn.sources.http import SourceRefused
    from finn.sources.nse import NSE

    with db.connection() as conn:
        db.migrate(conn)
        ids = list(ingest.company_ids(conn, ingest.demo_symbols()).values())
        print("  rules        ", pipeline.classify_rules_stage(conn, ids))
        try:
            print("  thin texts   ", pipeline.fetch_thin_texts(conn, NSE(), ids))
            print("  rules (text) ", pipeline.classify_rules_stage(conn, ids))
        except SourceRefused as e:
            print(f"!! STOPPED: {e}. Access rule: do not retry; tell the owner.")
            return 1
        if not args.no_llm:
            try:
                print("  model        ", pipeline.classify_llm_stage(conn, Router(store=LLMStore()), ids))
                print("  post-check   ", pipeline.drop_foreign_one_liners(conn))
            except LLMUnavailable as e:
                print(f"  model         skipped ({e}); undecided filings show as 'not yet classified'")
        print("  results cards", pipeline.compute_results_cards(conn, ids))
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        print("  network      ", network_views.materialise(conn, now))
        print("  alerts       ", alerts.materialise(conn, now))
        from finn.llm import ledger

        print("  cost ledger  ", ledger.materialise(conn))
        print("  briefs       ", brief.materialise(conn, now))
    return 0


def cmd_network(args: argparse.Namespace) -> int:
    """Seed the synthetic network (+ planted overlaps with executives in filings) and materialise
    the network views. `--seed` wipes and reloads this tenant's synthetic contacts."""
    from zoneinfo import ZoneInfo

    from finn.network import service, store

    with db.connection() as conn:
        db.migrate(conn)
        if args.seed:
            print("  synthetic    ", store.load_synthetic(conn))
            print("  overlaps     ", store.seed_overlaps(conn))
        print("  views        ", service.materialise(conn, datetime.now(ZoneInfo("Asia/Kolkata"))))
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Pull: build the research view for any NSE symbols (fetches missing transcripts politely)."""
    from finn.llm.router import Router
    from finn.llm.store import LLMStore
    from finn.pull import research
    from finn.sources.http import SourceRefused
    from finn.sources.nse import NSE

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    router = None if args.no_llm else Router(store=LLMStore())
    with db.connection() as conn:
        db.migrate(conn)
        for sym in syms:
            try:
                nse = None if args.offline else NSE()
                print(f"  {sym:<12}", research.materialise(conn, sym, router, nse))
            except SourceRefused as e:
                print(f"!! STOPPED: {e}. Access rule: do not retry; tell the owner.")
                return 1
            except ValueError as e:
                print(f"  {sym:<12} skipped: {e}")
        from finn.llm import ledger

        print("  cost ledger", ledger.materialise(conn))
    return 0


def cmd_import_transcripts(args: argparse.Namespace) -> int:
    """Ingest transcripts downloaded by hand into data/manual/<SYMBOL>/ (with manifest.json)."""
    from finn.config import REPO_ROOT
    from finn.pull.transcripts import import_manual

    with db.connection() as conn:
        db.migrate(conn)
        for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
            # data/ir: fetched by FINN from the company's IR site; data/manual: put there by the owner
            for root in ("ir", "manual"):
                if (REPO_ROOT / "data" / root / sym / "manifest.json").exists():
                    for line in import_manual(conn, sym, REPO_ROOT / "data" / root):
                        print(f"  {sym:<12} [{root}] {line}")
    return 0


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
        choices=["symbols", "holdings", "prices", "filings", "transcripts", "fundamentals", "texts", "all"],
    )
    ing.add_argument("--symbols", default="", help="comma-separated; default = demo set")
    ing.add_argument("--days", type=int, default=120)
    ing.set_defaults(fn=cmd_ingest)
    push = sub.add_parser("push", help="classify, results cards, materialise briefs")
    push.add_argument("--no-llm", action="store_true", help="rules only (e.g. on a CI runner)")
    push.set_defaults(fn=cmd_push)
    net = sub.add_parser("network", help="seed the synthetic network and materialise network views")
    net.add_argument(
        "--seed", action="store_true", help="reload synthetic contacts (destructive for tenant 1)"
    )
    net.set_defaults(fn=cmd_network)
    rs = sub.add_parser("research", help="build research views (pull) for symbols")
    rs.add_argument("symbols", help="comma-separated NSE symbols")
    rs.add_argument("--no-llm", action="store_true", help="rules-only guidance extraction")
    rs.add_argument("--offline", action="store_true", help="never fetch: use cached documents only")
    rs.set_defaults(fn=cmd_research)
    imp = sub.add_parser(
        "import-transcripts", help="ingest transcripts from data/ir/<SYMBOL>/ and data/manual/<SYMBOL>/"
    )
    imp.add_argument("symbols", help="comma-separated NSE symbols")
    imp.set_defaults(fn=cmd_import_transcripts)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
