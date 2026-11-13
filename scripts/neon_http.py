"""Mirror Neon <-> local Postgres over Neon's HTTPS SQL endpoint (port 443).

For networks that reset Postgres connections on 5432 (seen 2026-11-13 on the owner's Wi-Fi).
    python scripts/neon_http.py sizes
    python scripts/neon_http.py pull  [table ...]     # Neon -> LOCAL_URL (default finn_mirror)
    python scripts/neon_http.py push-views research:  # pipeline-owned views only
    python scripts/neon_http.py push-llm              # cache insert-only; ledger rows appended
    python scripts/neon_http.py push-documents        # new docs by url; never overwrites text
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
from finn.config import REPO_ROOT  # noqa: E402

# The remote is read from .env only (never from a shell DATABASE_URL, which may point at the
# local mirror while working), and must be a Neon host.
REMOTE = next(
    (
        ln.split("=", 1)[1].strip().strip('"')
        for ln in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if ln.startswith("DATABASE_URL=")
    ),
    "",
)
if not (urlparse(REMOTE).hostname or "").endswith(".neon.tech"):
    raise SystemExit("refused: DATABASE_URL in .env is not a Neon host")
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


# Write-back is allowlisted and can never overwrite what the live app writes.
#   views      : only pipeline-owned key prefixes; the app never writes these.
#   llm_cache  : insert-only (content-addressed: same key = same answer).
#   llm_calls  : insert-only, no id (Neon assigns), de-duplicated on (ts, purpose, model).
#   documents  : new rows by url only, no id (Neon assigns); an existing url is never touched
#                except to fill pages/source where Neon has none.
# Anything else (jobs, feedback, settings, ...) is refused.
PIPELINE_VIEW_PREFIXES = ("research:", "network:", "brief:", "alerts:", "coverage:", "cost:")


def _local(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(LOCAL) as lc:
        return [r[0] for r in lc.execute(sql, params).fetchall()]


def push_views(prefix: str) -> int:
    if not prefix.startswith(PIPELINE_VIEW_PREFIXES):
        raise SystemExit(f"refused: '{prefix}' is not a pipeline-owned view prefix {PIPELINE_VIEW_PREFIXES}")
    rows = _local("SELECT to_jsonb(x) FROM views x WHERE key LIKE %s", (prefix + "%",))
    for j in rows:
        q(
            "INSERT INTO views (key, body, as_of) VALUES ($1, $2::jsonb, $3::timestamptz) ON CONFLICT (key) "
            "DO UPDATE SET body = EXCLUDED.body, as_of = EXCLUDED.as_of, updated_at = now()",
            [j["key"], json.dumps(j["body"], ensure_ascii=False), j["as_of"]],
        )
    return len(rows)


def push_llm() -> tuple[int, int]:
    cache = _local("SELECT to_jsonb(x) FROM llm_cache x")
    for j in cache:
        q(
            "INSERT INTO llm_cache SELECT * FROM jsonb_populate_record(null::llm_cache, $1::jsonb) "
            "ON CONFLICT DO NOTHING",
            [json.dumps(j, ensure_ascii=False)],
        )
    calls = _local("SELECT to_jsonb(x) - 'id' FROM llm_calls x")
    n = 0
    for j in calls:
        r = q(
            "INSERT INTO llm_calls SELECT (jsonb_populate_record(null::llm_calls, "
            "$1::jsonb || jsonb_build_object('id', nextval(pg_get_serial_sequence('llm_calls', 'id'))))).* "
            "WHERE NOT EXISTS (SELECT 1 FROM llm_calls WHERE ts = ($1::jsonb->>'ts')::timestamptz "
            "AND purpose = $1::jsonb->>'purpose' "
            "AND coalesce(model, '') = coalesce($1::jsonb->>'model', '')) "
            "RETURNING 1",
            [json.dumps(j, ensure_ascii=False)],
        )
        n += len(r)
    return len(cache), n


def push_documents() -> tuple[int, int]:
    q("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'NSE'")
    rows = _local(
        "SELECT to_jsonb(d) - 'id' || jsonb_build_object('symbol', c.nse_symbol) FROM documents d "
        "JOIN companies c ON c.id = d.company_id WHERE d.pages IS NOT NULL"
    )
    new = filled = 0
    for j in rows:
        sym = j.pop("symbol")
        r = q(
            "INSERT INTO documents (company_id, kind, period, filed_at, url, sha256, n_pages, pages, "
            "fetched_at, source) SELECT c.id, $2, $3, $4::timestamptz, $5, $6, $7::int, $8::jsonb, "
            "$9::timestamptz, $10 FROM companies c WHERE c.nse_symbol = $1 "
            "ON CONFLICT (url) DO UPDATE SET pages = EXCLUDED.pages, n_pages = EXCLUDED.n_pages, "
            "sha256 = EXCLUDED.sha256, fetched_at = EXCLUDED.fetched_at "
            "WHERE documents.pages IS NULL RETURNING (xmax = 0) AS inserted",
            [
                sym,
                j["kind"],
                j.get("period"),
                j["filed_at"],
                j["url"],
                j.get("sha256"),
                j.get("n_pages"),
                json.dumps(j["pages"], ensure_ascii=False),
                j.get("fetched_at"),
                j.get("source", "NSE"),
            ],
        )
        for x in r:
            if x["inserted"]:
                new += 1
            else:
                filled += 1
    return new, filled


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["sizes"]
    if cmd == "sizes":
        sizes()
    elif cmd == "pull":
        pull(args)
    elif cmd == "push-views":
        print("views pushed:", push_views(args[0] if args else ""))
    elif cmd == "push-llm":
        print("llm_cache offered / llm_calls inserted:", push_llm())
    elif cmd == "push-documents":
        print("documents new / text filled:", push_documents())
    else:
        raise SystemExit(__doc__)
