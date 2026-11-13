"""Live research on demand: a job queue in Postgres (item 4).

Flow: the app asks for a symbol → the API validates it against the NSE master already in
`companies`, returns the cached report if one exists, joins an active job for the same symbol, or
writes a new job after the rate limits. A worker claims it: the owner's laptop if it has sent a
heartbeat recently, otherwise the API starts one GitHub Actions run for that job. The worker
fetches politely (sources/http.py rules), builds the research view and records progress after
every step, so the phone can show where the job is, including a runner that hasn't started yet.

Every limit below is a policy constant here, not scattered through the code.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import socket
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from finn.config import get_settings

log = logging.getLogger("finn.jobs")

MAX_RUNNING = 2  # concurrent research runs, all runners together
PER_REQUESTER_HOUR = 3  # new jobs per client per hour
PER_REQUESTER_DAY = 6
GLOBAL_DAY = 20  # new jobs per day, everyone together (free-tier model quotas)
WORKER_FRESH = timedelta(seconds=90)  # a laptop heartbeat newer than this = online
START_TIMEOUT = timedelta(minutes=10)  # dispatched but no runner started → failed
STALL_TIMEOUT = timedelta(minutes=12)  # running but no heartbeat → failed
ACTIVE = ("queued", "dispatched", "running")
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")

STEPS = [
    ("listing", "Transcript links from NSE announcements"),
    ("results", "Quarterly results (XBRL) from NSE"),
    ("research", "Read transcripts, extract guidance, resolve against results"),
]


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def requester_id(ip: str | None) -> str:
    """Salted hash of the client address, so limits work without storing the address."""
    salt = get_settings().database_url
    return hashlib.sha256(f"{salt}|{ip or 'unknown'}".encode()).hexdigest()[:16]


def _now() -> datetime:
    return datetime.now(UTC)


# -- reading ------------------------------------------------------------------------------------
COLS = (
    "id, symbol, status, runner, requested_at, dispatched_at, claimed_at, heartbeat_at, "
    "finished_at, steps, message, run_url"
)


def _row(r: tuple) -> dict:
    keys = [c.strip() for c in COLS.split(",")]
    d = dict(zip(keys, r, strict=True))
    for k in ("requested_at", "dispatched_at", "claimed_at", "heartbeat_at", "finished_at"):
        d[k] = d[k].isoformat() if d[k] else None
    return d


def laptop_online(conn: Connection) -> bool:
    r = conn.execute(
        "SELECT 1 FROM workers WHERE kind = 'laptop' AND last_seen > now() - %s", (WORKER_FRESH,)
    ).fetchone()
    return r is not None


def blocked(conn: Connection, origin: str, source: str = "NSE") -> dict | None:
    r = conn.execute(
        "SELECT at, detail FROM source_blocks WHERE origin = %s AND source = %s", (origin, source)
    ).fetchone()
    return {"at": r[0].isoformat(), "detail": r[1]} if r else None


def startup_stats(conn: Connection) -> dict:
    """Measured GitHub runner start-up (dispatch → claimed), so the UI quotes data, not a guess."""
    r = conn.execute(
        "SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY w), max(w) FROM ("
        " SELECT extract(epoch FROM claimed_at - dispatched_at) AS w FROM research_jobs"
        " WHERE runner = 'github' AND claimed_at IS NOT NULL AND dispatched_at IS NOT NULL) x"
    ).fetchone()
    n, med, mx = r if r else (0, None, None)
    return {"runs": int(n or 0), "median_s": round(med) if med else None, "max_s": round(mx) if mx else None}


def describe(conn: Connection, job: dict) -> dict:
    """The job plus what the app should say about it, in plain words."""
    online = laptop_online(conn)
    gh_block = blocked(conn, "github")
    s = job["status"]
    if s == "queued":
        if online:
            note = "Queued. The owner's laptop worker is online and picks up jobs within about 20 seconds."
        elif gh_block:
            note = (
                "Waiting. NSE refused GitHub's servers on "
                f"{gh_block['at'][:10]}, so FINN doesn't send new tickers there, and the owner's laptop "
                "worker is offline. A new ticker can't be fetched right now; this job runs when the "
                "laptop is next online."
            )
        else:
            note = f"Queued behind {MAX_RUNNING} running jobs; it starts when one finishes."
    elif s == "dispatched":
        st = startup_stats(conn)
        waited = (_now() - datetime.fromisoformat(job["dispatched_at"])).total_seconds()
        typical = (
            f"Measured so far: median {st['median_s']} s, slowest {st['max_s']} s over {st['runs']} runs."
            if st["runs"]
            else "No start-up time measured yet."
        )
        note = f"Asked GitHub for a runner {round(waited)} s ago; it hasn't started yet. {typical}"
    elif s == "running":
        note = f"Running on {'the owner laptop' if job['runner'] == 'laptop' else 'a GitHub Actions runner'}."
    elif s == "done":
        note = job["message"] or "Done."
    else:
        note = job["message"] or s
    return {**job, "note": note, "laptop_online": online}


def get(conn: Connection, job_id: int) -> dict | None:
    tick(conn)
    r = conn.execute(f"SELECT {COLS} FROM research_jobs WHERE id = %s", (job_id,)).fetchone()
    return describe(conn, _row(r)) if r else None


# -- requesting ---------------------------------------------------------------------------------
def request(
    conn: Connection, symbol: str, ip: str | None, dispatch: Callable[[int], str | None] | None = None
) -> dict:
    """Validate, dedupe, rate-limit, enqueue, and start a runner if needed. Returns
    {"state": "cached"|"job", ...}. Raises JobError with an HTTP status and a plain message."""
    sym = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(sym):
        raise JobError(422, "bad_symbol", "That isn't an NSE symbol (letters, digits, & or -).")
    row = conn.execute("SELECT id, name FROM companies WHERE nse_symbol = %s", (sym,)).fetchone()
    if row is None:
        raise JobError(404, "unknown_symbol", f"{sym} isn't in NSE's list of listed equities.")
    cid, name = row
    if conn.execute("SELECT 1 FROM views WHERE key = %s", (f"research:{sym}",)).fetchone():
        return {"state": "cached", "symbol": sym, "name": name}
    tick(conn)
    act = conn.execute(
        f"SELECT {COLS} FROM research_jobs WHERE symbol = %s AND status = ANY(%s)", (sym, list(ACTIVE))
    ).fetchone()
    if act:
        return {"state": "job", "joined": True, "job": describe(conn, _row(act))}
    who = requester_id(ip)
    hour, day = conn.execute(
        "SELECT count(*) FILTER (WHERE requested_at > now() - interval '1 hour'), "
        "count(*) FILTER (WHERE requested_at > now() - interval '1 day') "
        "FROM research_jobs WHERE requester = %s",
        (who,),
    ).fetchone()  # type: ignore[misc]
    if hour >= PER_REQUESTER_HOUR or day >= PER_REQUESTER_DAY:
        raise JobError(
            429,
            "rate_limited",
            f"Limit reached: {PER_REQUESTER_HOUR} new tickers an hour, {PER_REQUESTER_DAY} a day from "
            "one connection. Already-researched tickers open instantly.",
        )
    (total,) = conn.execute(
        "SELECT count(*) FROM research_jobs WHERE requested_at > now() - interval '1 day'"
    ).fetchone()  # type: ignore[misc]
    if total >= GLOBAL_DAY:
        raise JobError(
            429,
            "daily_cap",
            f"FINN has run its {GLOBAL_DAY} new-ticker jobs for today (free model quotas). "
            "Researched tickers still open instantly.",
        )
    try:
        (jid,) = conn.execute(
            "INSERT INTO research_jobs (symbol, company_id, requester, steps) VALUES (%s, %s, %s, %s) "
            "RETURNING id",
            (sym, cid, who, Jsonb([{"name": n, "label": lbl, "state": "pending"} for n, lbl in STEPS])),
        ).fetchone()  # type: ignore[misc]
        conn.commit()
    except errors.UniqueViolation:  # another request for the same symbol won the race: join it
        conn.rollback()
        act = conn.execute(
            f"SELECT {COLS} FROM research_jobs WHERE symbol = %s AND status = ANY(%s)", (sym, list(ACTIVE))
        ).fetchone()
        return {"state": "job", "joined": True, "job": describe(conn, _row(act))}  # type: ignore[arg-type]
    schedule(conn, dispatch)
    return {"state": "job", "joined": False, "job": get(conn, jid)}


# -- scheduling ---------------------------------------------------------------------------------
def tick(conn: Connection) -> None:
    """Expire runs that never started or stopped reporting. Cheap; called on every read."""
    conn.execute(
        "UPDATE research_jobs SET status = 'failed', finished_at = now(), message = %s "
        "WHERE status = 'dispatched' AND dispatched_at < now() - %s",
        (
            "The GitHub runner never started (GitHub queues free runners; nothing was fetched). Ask again.",
            START_TIMEOUT,
        ),
    )
    conn.execute(
        "UPDATE research_jobs SET status = 'failed', finished_at = now(), message = %s "
        "WHERE status = 'running' AND coalesce(heartbeat_at, claimed_at) < now() - %s",
        (
            "The worker stopped reporting mid-run. Anything it fetched is cached; asking again resumes.",
            STALL_TIMEOUT,
        ),
    )
    conn.commit()


def schedule(conn: Connection, dispatch: Callable[[int], str | None] | None = None) -> list[int]:
    """Start GitHub runs for queued jobs while there is capacity and no laptop worker online.
    The laptop claims queued jobs itself. Never sends work to an origin NSE has refused."""
    if laptop_online(conn) or blocked(conn, "github"):
        return []
    dispatch = dispatch or github_dispatch
    started = []
    while True:
        (busy,) = conn.execute(
            "SELECT count(*) FROM research_jobs WHERE status IN ('dispatched', 'running')"
        ).fetchone()  # type: ignore[misc]
        if busy >= MAX_RUNNING:
            break
        r = conn.execute(
            "SELECT id FROM research_jobs WHERE status = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        ).fetchone()
        if r is None:
            break
        err = dispatch(r[0])
        if err:
            conn.execute(
                "UPDATE research_jobs SET status = 'failed', finished_at = now(), message = %s WHERE id = %s",
                (f"Couldn't start a GitHub runner: {err}", r[0]),
            )
        else:
            conn.execute(
                "UPDATE research_jobs SET status = 'dispatched', dispatched_at = now() WHERE id = %s", (r[0],)
            )
            started.append(r[0])
        conn.commit()
    return started


def github_dispatch(job_id: int) -> str | None:
    """POST a workflow_dispatch for research.yml. Returns an error string, or None on success."""
    s = get_settings()
    repo = s.github_repo or os.environ.get("RENDER_GIT_REPO_SLUG", "")
    if not (s.github_dispatch_token and repo):
        return "no dispatch token or repository configured on the API"
    try:
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/research.yml/dispatches",
            headers={
                "Authorization": f"Bearer {s.github_dispatch_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": s.github_ref, "inputs": {"job_id": str(job_id)}},
            timeout=15,
        )
    except httpx.HTTPError as e:
        return f"GitHub unreachable ({type(e).__name__})"
    return None if r.status_code == 204 else f"GitHub answered HTTP {r.status_code}"


# -- worker side --------------------------------------------------------------------------------
def heartbeat(conn: Connection, name: str, kind: str) -> None:
    conn.execute(
        "INSERT INTO workers (name, kind, last_seen) VALUES (%s, %s, now()) "
        "ON CONFLICT (name) DO UPDATE SET last_seen = now(), kind = EXCLUDED.kind",
        (name, kind),
    )
    conn.commit()


def claim(
    conn: Connection, runner: str, job_id: int | None = None, run_url: str | None = None
) -> dict | None:
    """Take one job: a specific one (GitHub run started for it) or the oldest queued (laptop).
    Respects MAX_RUNNING; returns None when there is nothing to do."""
    (busy,) = conn.execute("SELECT count(*) FROM research_jobs WHERE status = 'running'").fetchone()  # type: ignore[misc]
    if busy >= MAX_RUNNING:
        return None
    args: tuple = ()
    if job_id is not None:
        q, args = "id = %s AND status IN ('queued', 'dispatched')", (job_id,)
    else:
        q = "status = 'queued'"
    r = conn.execute(
        "UPDATE research_jobs SET status = 'running', runner = %s, claimed_at = now(), "
        "heartbeat_at = now(), run_url = coalesce(%s, run_url) "
        f"WHERE id = (SELECT id FROM research_jobs WHERE {q} ORDER BY id "
        f"LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING {COLS}",
        (runner, run_url, *args),
    ).fetchone()
    conn.commit()
    return _row(r) if r else None


def step(conn: Connection, job_id: int, name: str, state: str, detail: str = "") -> None:
    (steps,) = conn.execute("SELECT steps FROM research_jobs WHERE id = %s", (job_id,)).fetchone()  # type: ignore[misc]
    for s in steps:
        if s["name"] == name:
            s.update(state=state, detail=detail, at=_now().isoformat())
    conn.execute(
        "UPDATE research_jobs SET steps = %s, heartbeat_at = now() WHERE id = %s", (Jsonb(steps), job_id)
    )
    conn.commit()


def finish(conn: Connection, job_id: int, status: str, message: str) -> None:
    conn.execute(
        "UPDATE research_jobs SET status = %s, message = %s, finished_at = now() WHERE id = %s",
        (status, message, job_id),
    )
    conn.commit()


def record_block(conn: Connection, origin: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO source_blocks (origin, source, detail) VALUES (%s, 'NSE', %s) ON CONFLICT DO NOTHING",
        (origin, detail[:500]),
    )
    conn.commit()


class Beat:
    """Background heartbeat for a running job (and the laptop worker) on its own connection, so a
    long model step doesn't look like a stalled worker."""

    def __init__(self, job_id: int, worker: str | None, every: float = 30.0) -> None:
        import threading

        self.job_id, self.worker, self.every = job_id, worker, every
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        from finn import db

        while not self._stop.wait(self.every):
            try:
                with db.connection() as c:
                    c.execute("UPDATE research_jobs SET heartbeat_at = now() WHERE id = %s", (self.job_id,))
                    if self.worker:
                        heartbeat(c, self.worker, "laptop")
                    c.commit()
            except Exception as e:  # a missed beat is not fatal; the stall timeout is generous
                log.warning("heartbeat failed: %s", e)

    def __enter__(self) -> Beat:
        self._t.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()


def run(conn: Connection, job: dict, origin: str, nse_factory, router) -> str:
    with Beat(job["id"], worker_name() if origin == "laptop" else None):
        try:
            return _run(conn, job, origin, nse_factory, router)
        except Exception as e:
            conn.rollback()
            finish(conn, job["id"], "failed", f"The run failed: {type(e).__name__}: {str(e)[:200]}")
            raise


def _run(conn: Connection, job: dict, origin: str, nse_factory, router) -> str:
    """Execute one claimed job. NSE access goes through the polite client; a refusal is recorded
    permanently for this origin and the job finishes with whatever was already cached."""
    from finn import ingest
    from finn.pull import research
    from finn.sources.http import SourceRefused

    jid, sym = job["id"], job["symbol"]
    refused: str | None = None
    nse = None
    if origin != "laptop" and blocked(conn, origin):
        refused = f"NSE refused {origin} earlier; not asking again."
    else:
        try:
            nse = nse_factory()
        except SourceRefused as e:
            refused = str(e)
    work = [
        ("listing", lambda n: ingest.ingest_transcript_history(conn, n, [sym])),
        ("results", lambda n: ingest.ingest_fundamentals(conn, n, [sym])),
    ]
    for name, fn in work:
        if refused or nse is None:
            step(conn, jid, name, "skipped", "NSE unavailable from this runner; using the cache only")
            continue
        step(conn, jid, name, "running")
        try:
            out = fn(nse)
            step(conn, jid, name, "done", ", ".join(f"{k} {v}" for k, v in out.items()) or "nothing new")
        except SourceRefused as e:
            conn.rollback()
            refused = str(e)
            if origin != "laptop":  # the laptop's permanent record is its marker file
                record_block(conn, origin, refused)
            step(
                conn,
                jid,
                name,
                "refused",
                "NSE refused this runner. Recorded; FINN won't ask from here again.",
            )
    step(conn, jid, "research", "running")
    try:
        out = research.materialise(conn, sym, router, None if refused else nse, live=True)
    except SourceRefused as e:
        conn.rollback()
        refused = str(e)
        if origin != "laptop":
            record_block(conn, origin, refused)
        out = research.materialise(conn, sym, router, None, live=True)
    if not out["quarters"] and not out["calls"]:
        conn.execute("DELETE FROM views WHERE key = %s", (f"research:{sym}",))
        research.refresh_index(conn)
        why = (
            "NSE refused the request from this runner, and nothing for this company is cached."
            if refused
            else "NSE has no XBRL results or call transcripts for this company in the last two years."
        )
        step(conn, jid, "research", "empty", why)
        finish(conn, jid, "refused" if refused else "failed", why)
        return "empty"
    detail = f"{out['quarters']} quarters, {out['calls']} calls read, {out['guidance']} guidance items"
    step(conn, jid, "research", "done", detail)
    finish(
        conn,
        jid,
        "done",
        f"Report ready: {detail}."
        + (" NSE refused part of the fetch; built from what was cached." if refused else ""),
    )
    return "done"


def worker_name() -> str:
    return f"laptop:{socket.gethostname()}"
