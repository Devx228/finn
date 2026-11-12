"""FastAPI read API. The read path is a SELECT on materialised views; no model calls."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from finn import db
from finn.config import get_settings
from finn.models import Brief, Health, Window

log = logging.getLogger("finn.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close_pool()


app = FastAPI(title="FINN API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)


@app.get("/livez")
def livez() -> dict[str, str]:
    """Process liveness only — never touches the DB. The scheduled keep-alive pings this so the
    web service stays warm without keeping the free-tier Postgres awake (it has a monthly
    compute-hour budget and scales to zero when idle)."""
    return {"status": "ok"}


_last_probe = 0.0


@app.get("/api/_probe/nse")
def probe_nse() -> dict[str, object]:
    """TEMPORARY (Phase 1 probe 4): one plain request from the Render host to a fixed NSE URL.
    No user input reaches the URL; at most one call per 60 s. Removed after the probe."""
    import time

    import httpx

    global _last_probe
    if time.monotonic() - _last_probe < 60:
        raise HTTPException(status_code=429, detail="one probe per minute")
    _last_probe = time.monotonic()
    url = (
        "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=INFY"
        "&from_date=01-11-2026&to_date=12-11-2026"
    )
    t0 = time.monotonic()
    try:
        r = httpx.get(url, headers={"User-Agent": "FINN-prototype/0.1"}, timeout=30)
        return {
            "status": r.status_code,
            "bytes": len(r.content),
            "seconds": round(time.monotonic() - t0, 2),
            "content_type": r.headers.get("content-type"),
            "head": r.text[:120],
        }
    except Exception as exc:
        return {"error": type(exc).__name__, "detail": str(exc)[:200]}


@app.get("/health", response_model=Health)
def health() -> Health:
    db_state: Literal["ok", "down"] = "ok"
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # health must answer even when the DB is down
        log.warning("health: db unreachable: %s", exc)
        db_state = "down"
    return Health(
        status="ok" if db_state == "ok" else "degraded",
        env=get_settings().finn_env,
        db=db_state,
    )


@app.get("/api/brief", response_model=Brief)
def get_brief(window: Window = "24h") -> Brief:
    with db.connection() as conn:
        row = conn.execute("SELECT body FROM views WHERE key = %s", (f"brief:{window}",)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"status": "not_materialised"})
    return Brief.model_validate(row[0])
