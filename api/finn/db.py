"""Postgres access: a lazily opened connection pool and a tiny SQL-file migrator."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from finn.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=0,
            max_size=5,
            open=True,
            timeout=5,
            kwargs={"connect_timeout": 5},
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply every migrations/NNNN_*.sql not yet recorded. Returns names applied."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied
