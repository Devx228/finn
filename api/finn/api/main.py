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
