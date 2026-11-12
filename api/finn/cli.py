"""`finn` command line: the ingest side of the system. Phase 0 has wiring commands only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from finn import db
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
        BriefItem(
            id=f"p0-{window}-3", tier="buried", company="—", headline="Placeholder buried item"
        ),
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="finn")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    sub.add_parser("seed-placeholder").set_defaults(fn=cmd_seed_placeholder)
    ex = sub.add_parser("export-snapshot")
    ex.add_argument("--out", default=str(SNAPSHOT_DIR))
    ex.set_defaults(fn=cmd_export_snapshot)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
