"""Mirror Neon <-> local Postgres over Neon's HTTPS SQL endpoint (port 443).

For networks that reset Postgres connections on 5432 (seen 2026-11-13 on the owner's Wi-Fi).
    python scripts/neon_http.py sizes
    python scripts/neon_http.py pull  [table ...]     # Neon -> LOCAL_URL (default finn_mirror)
    python scripts/neon_http.py push-views [prefix]   # LOCAL views -> Neon (upsert)
    python scripts/neon_http.py push-table <table>    # LOCAL rows -> Neon (upsert on primary key)
Run from api/ with the venv: .venv/Scripts/python ../scripts/neon_http.py ...
Never prints the connection string.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse

import httpx
import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from finn.config import get_settings  # noqa: E402

REMOTE = get_settings().database_url
LOCAL = os.environ.get("LOCAL_URL", "postgresql://finn:finn@localhost:5432/finn_mirror")
HOST = urlparse(REMOTE).hostname
CLIENT = httpx.Client(timeout=120)


def q(sql: str, params: list | None = None) -> list[dict]:
    r = CLIENT.post(
        f"https://{HOST}/sql",
        headers={"Neon-Connection-String": REMOTE},
        json={"query": sql, "params": params or []},
    )
    if r.status_code != 200:
        raise RuntimeError(f"neon http {r.status_code}: {r.text[:300]}")
    return r.json()["rows"]


def tables() -> list[str]:
    rows = q(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
        "AND table_type='BASE TABLE' ORDER BY 1"
    )
    return [r["table_name"] for r in rows]


def pk(table: str) -> list[str]:
    rows = q(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid "
        "AND a.attnum = ANY(i.indkey) WHERE i.indrelid = $1::regclass AND i.indisprimary",
        [table],
    )
    return [r["attname"] for r in rows]


def sizes() -> None:
    for t in tables():
        n = q(f'SELECT count(*) n, pg_total_relation_size($1) b FROM "{t}"', [t])[0]
        print(f"{t:28s} {int(n['n']):>8,d} rows {int(n['b']) / 1e6:8.1f} MB")


def pull(only: list[str]) -> None:
    ts = only or tables()
    with psycopg.connect(LOCAL) as lc:
        lc.execute("SET session_replication_role = replica")  # no FK checks while loading
        lc.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in ts))  # once: per-table CASCADE wipes loaded rows
        for t in ts:
            keys = pk(t) or ["ctid"]
            order = ", ".join(f'"{k}"' for k in keys) if keys != ["ctid"] else "ctid"
            mb = int(q("SELECT pg_total_relation_size($1) b", [t])[0]["b"]) / 1e6
            n_rows = int(q(f'SELECT count(*) n FROM "{t}"')[0]["n"]) or 1
            page = max(20, min(5000, int(n_rows / max(mb / 4, 1))))  # ~4 MB per response
            off, total = 0, 0
            while True:
                rows = q(f'SELECT to_jsonb(x) j FROM "{t}" x ORDER BY {order} LIMIT {page} OFFSET {off}')
                if not rows:
                    break
                with lc.cursor() as cur:
                    cur.executemany(
                        f'INSERT INTO "{t}" SELECT * FROM jsonb_populate_record(null::"{t}", %s)',
                        [(Jsonb(r["j"]),) for r in rows],
                    )
                total += len(rows)
                off += page
            # keep sequences ahead of the copied ids
            for (seq_col,) in lc.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s "
                "AND column_default LIKE 'nextval%%'",
                (t,),
            ).fetchall():
                lc.execute(
                    f"SELECT setval(pg_get_serial_sequence('\"{t}\"', %s), "
                    f'coalesce((SELECT max("{seq_col}") FROM "{t}"), 0) + 1, false)',
                    (seq_col,),
                )
            lc.commit()
            print(f"{t}: {total} rows")


def push_rows(table: str, where: str = "TRUE", params: tuple = ()) -> int:
    keys = pk(table)
    with psycopg.connect(LOCAL) as lc:
        rows = lc.execute(f'SELECT to_jsonb(x) FROM "{table}" x WHERE {where}', params).fetchall()
    cols = list(rows[0][0].keys()) if rows else []
    upd = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in keys)
    conflict = f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {upd}" if keys and upd else ""
    for (j,) in rows:
        q(
            f'INSERT INTO "{table}" SELECT * FROM '
            f'jsonb_populate_record(null::"{table}", $1::jsonb) {conflict}',
            [json.dumps(j, ensure_ascii=False)],
        )
    return len(rows)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["sizes"]
    if cmd == "sizes":
        sizes()
    elif cmd == "pull":
        pull(args)
    elif cmd == "push-views":
        prefix = args[0] if args else ""
        print("views pushed:", push_rows("views", "key LIKE %s", (prefix + "%",)))
    elif cmd == "push-table":
        print(args[0], "rows pushed:", push_rows(args[0]))
    else:
        raise SystemExit(__doc__)
