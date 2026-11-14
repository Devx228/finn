"""FastAPI read API. The read path is a SELECT on materialised views; no model calls."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


def _view(key: str) -> dict:
    with db.connection() as conn:
        row = conn.execute("SELECT body FROM views WHERE key = %s", (key,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"status": "not_materialised", "key": key})
    return row[0]


@app.get("/api/network")
def get_network() -> dict:
    """The People tab: keep-warm nudges, people in filings with paths, expertise map, coverage."""
    return _view("network:home")


@app.get("/api/network/company/{symbol}")
def get_network_company(symbol: str) -> dict:
    """Who should I call about this company (ranked, with why and a compliance flag)."""
    return _view(f"network:company:{symbol.upper()}")


@app.get("/api/network/person/{person_id}")
def get_network_person(person_id: int) -> dict:
    """Diligence on a person named in a filing: career as disclosed, overlaps, second-degree paths."""
    return _view(f"network:person:{person_id}")


@app.get("/api/research/{symbol}")
def get_research(symbol: str) -> dict:
    """Pull: the research view (numbers from XBRL, guidance verbatim from transcripts)."""
    return _view(f"research:{symbol.upper()}")


@app.get("/api/research")
def list_research() -> dict:
    """Companies with a research view."""
    return _view("research:index")


@app.get("/api/cost")
def get_cost() -> dict:
    """Cost ledger: every model call (hit or miss), tokens, cache rate, filings decided by rules."""
    return _view("cost:summary")


@app.get("/api/alerts/inputs")
def get_alert_inputs() -> dict:
    """EOD bars + material filings for the holdings; rules are evaluated client-side (and in
    finn.push.alerts.evaluate, the same logic) so threshold changes apply instantly."""
    return _view("alerts:inputs")


class JobRequest(BaseModel):
    symbol: str


class CommandRequest(BaseModel):
    prompt: str


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushKeys


class PushSubscriptionRequest(BaseModel):
    subscription: PushSubscription


class PushTokenRequest(BaseModel):
    subscription_id: str


def _client_ip(req: Request) -> str | None:
    # Render puts the caller first in X-Forwarded-For; locally there is no proxy
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (req.client.host if req.client else None)


@app.get("/api/command/catalog")
def get_command_catalog() -> dict:
    """Listed-company names for deterministic client-side symbol/company routing."""
    from finn import command

    with db.connection() as conn:
        return command.catalog(conn)


@app.post("/api/command")
def run_command(body: CommandRequest, req: Request) -> dict:
    """Rules missed: a model selects typed tools; code returns cited blocks from stored data."""
    from finn import command
    from finn.llm.router import LLMUnavailable, Router
    from finn.llm.store import LLMStore

    with db.connection() as conn:
        try:
            return command.answer(conn, body.prompt, _client_ip(req), Router(store=LLMStore()))
        except command.JobError as e:
            raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message}) from e
        except LLMUnavailable as e:
            log.warning("command model unavailable: %s", e)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "model_unavailable",
                    "message": "The command model is unavailable. Symbol and People routes still work.",
                },
            ) from e


@app.get("/api/push/config")
def get_push_config() -> dict:
    from finn import web_push

    return web_push.config()


@app.post("/api/push/subscribe")
def subscribe_push(body: PushSubscriptionRequest, req: Request) -> dict:
    from finn import web_push

    with db.connection() as conn:
        try:
            return web_push.subscribe(conn, body.subscription.model_dump(), _client_ip(req))
        except web_push.JobError as e:
            raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message}) from e


@app.post("/api/push/unsubscribe")
def unsubscribe_push(body: PushTokenRequest) -> dict:
    from finn import web_push

    with db.connection() as conn:
        return web_push.unsubscribe(conn, body.subscription_id)


@app.post("/api/push/test")
def test_push(body: PushTokenRequest, req: Request) -> dict:
    from finn import web_push

    with db.connection() as conn:
        try:
            return web_push.send_test(conn, body.subscription_id, _client_ip(req))
        except web_push.JobError as e:
            raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message}) from e


@app.post("/api/research/jobs")
def create_research_job(body: JobRequest, req: Request) -> dict:
    """Research a ticker that has no report yet. Validated against the NSE master; a cached report
    is returned as-is; one live job per symbol; rate-limited per client and per day."""
    from finn import jobs

    with db.connection() as conn:
        try:
            return jobs.request(conn, body.symbol, _client_ip(req))
        except jobs.JobError as e:
            raise HTTPException(status_code=e.status, detail={"code": e.code, "message": e.message}) from e


@app.get("/api/research/jobs/{job_id}")
def get_research_job(job_id: int) -> dict:
    """Progress of a research job, with a plain-words note on where it is (incl. runner start-up)."""
    from finn import jobs

    with db.connection() as conn:
        j = jobs.get(conn, job_id)
        if j is not None and j["status"] == "queued":
            jobs.schedule(conn)  # capacity may have freed since it was queued
            j = jobs.get(conn, job_id)
    if j is None:
        raise HTTPException(status_code=404, detail={"code": "no_job", "message": "No such job."})
    return j
