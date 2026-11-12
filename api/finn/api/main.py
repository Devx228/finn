"""FastAPI read API. The read path is a SELECT on materialised views; no model calls."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from finn import db
from finn.config import get_settings
from finn.models import Brief, Health, Window

log = logging.getLogger("finn.api")
IST = ZoneInfo("Asia/Kolkata")


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
def get_brief(window: Window = "24h", as_of: date | None = None) -> Brief:
    """The materialised brief. With `as_of`, replay the brief at 9 pm IST on that date (built
    from stored filings, classifications and cards — SQL and code only, never a model call)."""
    with db.connection() as conn:
        if as_of is not None:
            if not (date(2020, 1, 1) <= as_of <= date.today()):
                raise HTTPException(status_code=422, detail="as_of out of range")
            from finn.push.brief import build_brief

            at = datetime.combine(as_of, time(21, 0), tzinfo=IST)
            return Brief.model_validate(build_brief(conn, window, at))
        row = conn.execute("SELECT body FROM views WHERE key = %s", (f"brief:{window}",)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"status": "not_materialised"})
    return Brief.model_validate(row[0])
