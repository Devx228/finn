from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from finn import db
from finn.api.main import app
from finn.cli import main as cli_main
from finn.cli import placeholder_brief


def _db_up() -> bool:
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_up(), reason="local Postgres not running")
client = TestClient(app)


def test_placeholder_brief_counts_match_items():
    b = placeholder_brief("24h", datetime.now(UTC))
    assert b.placeholder is True
    assert b.counts.filings == len(b.items)
    for tier in ("now", "worth", "buried"):
        assert getattr(b.counts, tier) == sum(i.tier == tier for i in b.items)


def test_health_degrades_when_db_down(monkeypatch):
    def boom():
        raise OSError("no db")

    monkeypatch.setattr(db, "connection", boom)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "down" and r.json()["status"] == "degraded"


def test_livez_never_touches_db(monkeypatch):
    def boom():
        raise AssertionError("livez must not open a DB connection")

    monkeypatch.setattr(db, "connection", boom)
    r = client.get("/livez")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_brief_rejects_unknown_window():
    assert client.get("/api/brief?window=2h").status_code == 422


@needs_db
def test_migrate_is_idempotent():
    assert cli_main(["migrate"]) == 0
    with db.connection() as conn:
        assert db.migrate(conn) == []


@needs_db
def test_brief_round_trip_from_postgres():
    assert cli_main(["migrate"]) == 0
    assert cli_main(["seed-placeholder"]) == 0
    r = client.get("/api/brief?window=7d")
    assert r.status_code == 200
    body = r.json()
    assert body["window"] == "7d" and body["placeholder"] is True
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["db"] == "ok"
