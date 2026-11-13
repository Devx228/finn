"""Live research job queue: validation, cache, dedupe, limits, capacity, runner choice, refusal."""

import pytest
from fastapi.testclient import TestClient
from test_phase0 import needs_db

from finn import db, jobs
from finn.api.main import app
from finn.sources.http import SourceRefused

SYMS = [f"ZZT{i}" for i in range(6)]


@pytest.fixture
def conn():
    with db.connection() as c:
        db.migrate(c)

        def clean():
            c.execute("DELETE FROM research_jobs WHERE symbol LIKE 'ZZT%'")
            c.execute("DELETE FROM views WHERE key LIKE 'research:ZZT%'")
            c.execute("DELETE FROM workers WHERE name LIKE 'test:%'")
            c.execute("DELETE FROM source_blocks WHERE origin = 'test-origin'")
            c.execute("DELETE FROM companies WHERE nse_symbol LIKE 'ZZT%'")
            c.commit()

        clean()
        # other tests' live jobs would count against capacity
        c.execute(
            "UPDATE research_jobs SET status = 'failed' WHERE status IN ('queued','dispatched','running')"
        )
        c.execute("DELETE FROM workers WHERE kind = 'laptop'")
        for s in SYMS:
            c.execute("INSERT INTO companies (nse_symbol, name) VALUES (%s, %s)", (s, f"{s} Ltd"))
        c.commit()
        yield c
        clean()


class Dispatch:
    def __init__(self, err=None):
        self.ids, self.err = [], err

    def __call__(self, jid):
        self.ids.append(jid)
        return self.err


@needs_db
def test_validates_symbol_against_the_master(conn):
    with pytest.raises(jobs.JobError) as e:
        jobs.request(conn, "rm -rf", "1.1.1.1", Dispatch())
    assert e.value.status == 422
    with pytest.raises(jobs.JobError) as e:
        jobs.request(conn, "NOTALISTEDCO", "1.1.1.1", Dispatch())
    assert e.value.status == 404


@needs_db
def test_cached_report_is_returned_without_a_job(conn):
    conn.execute("INSERT INTO views (key, body, as_of) VALUES ('research:ZZT0', '{}', now())")
    conn.commit()
    d = Dispatch()
    assert jobs.request(conn, "zzt0", "1.1.1.1", d)["state"] == "cached"
    assert d.ids == []


@needs_db
def test_one_job_per_symbol_and_one_runner(conn):
    d = Dispatch()
    a = jobs.request(conn, "ZZT1", "1.1.1.1", d)
    b = jobs.request(conn, "ZZT1", "2.2.2.2", d)
    assert a["job"]["id"] == b["job"]["id"] and b["joined"]
    assert d.ids == [a["job"]["id"]]
    assert a["job"]["status"] == "dispatched" and "hasn't started yet" in a["job"]["note"]


@needs_db
def test_per_client_limit(conn):
    d = Dispatch()
    for s in SYMS[:3]:
        jobs.request(conn, s, "9.9.9.9", d)
    with pytest.raises(jobs.JobError) as e:
        jobs.request(conn, SYMS[3], "9.9.9.9", d)
    assert e.value.status == 429
    assert jobs.request(conn, SYMS[3], "8.8.8.8", d)["state"] == "job"  # other clients unaffected


@needs_db
def test_capacity_queues_beyond_max_running(conn):
    d = Dispatch()
    out = [jobs.request(conn, s, f"10.0.0.{i}", d)["job"] for i, s in enumerate(SYMS[:3])]
    assert [j["status"] for j in out] == ["dispatched", "dispatched", "queued"]
    assert len(d.ids) == jobs.MAX_RUNNING
    jobs.finish(conn, out[0]["id"], "done", "ok")
    assert jobs.schedule(conn, d) == [out[2]["id"]]


@needs_db
def test_laptop_online_means_no_github_run(conn):
    jobs.heartbeat(conn, "test:laptop", "laptop")
    d = Dispatch()
    j = jobs.request(conn, "ZZT2", "1.1.1.1", d)["job"]
    assert d.ids == [] and j["status"] == "queued" and "laptop worker is online" in j["note"]
    got = jobs.claim(conn, "laptop")
    assert got and got["id"] == j["id"] and got["status"] == "running"


@needs_db
def test_failed_dispatch_is_reported_honestly(conn):
    j = jobs.request(conn, "ZZT3", "1.1.1.1", Dispatch(err="GitHub answered HTTP 401"))["job"]
    assert j["status"] == "failed" and "HTTP 401" in j["message"]


class RefusingNSE:
    def __init__(self):
        self.http = self

    def announcements(self, *a):
        raise SourceRefused("NSE: HTTP 403 Access Denied")

    results_filings = annual_reports = announcements


@needs_db
def test_refusal_is_recorded_permanently_and_job_says_why(conn):
    d = Dispatch()
    j = jobs.request(conn, "ZZT4", "1.1.1.1", d)["job"]
    job = jobs.claim(conn, "github", job_id=j["id"])
    assert jobs.run(conn, job, "test-origin", RefusingNSE, router=None) == "empty"
    got = jobs.get(conn, j["id"])
    assert got["status"] == "refused" and "refused" in got["message"]
    assert jobs.blocked(conn, "test-origin")
    assert conn.execute("SELECT 1 FROM views WHERE key = 'research:ZZT4'").fetchone() is None
    # a later job on the same origin doesn't ask NSE at all
    calls = []

    class Spy(RefusingNSE):
        def announcements(self, *a):
            calls.append(a)
            raise AssertionError("must not be called")

    jobs.finish(conn, j["id"], "failed", "reset")
    j2 = jobs.request(conn, "ZZT5", "1.1.1.2", d)["job"]
    jobs.run(conn, jobs.claim(conn, "github", job_id=j2["id"]), "test-origin", Spy, router=None)
    assert calls == []


@needs_db
def test_runner_that_never_starts_expires(conn):
    j = jobs.request(conn, "ZZT1", "1.1.1.1", Dispatch())["job"]
    conn.execute(
        "UPDATE research_jobs SET dispatched_at = now() - interval '11 minutes' WHERE id = %s", (j["id"],)
    )
    conn.commit()
    got = jobs.get(conn, j["id"])
    assert got["status"] == "failed" and "never started" in got["message"]


@needs_db
def test_api_endpoints(conn, monkeypatch):
    monkeypatch.setattr(jobs, "github_dispatch", lambda jid: None)
    c = TestClient(app)
    r = c.post("/api/research/jobs", json={"symbol": "ZZT1"}, headers={"x-forwarded-for": "7.7.7.7"})
    assert r.status_code == 200 and r.json()["state"] == "job"
    jid = r.json()["job"]["id"]
    assert c.get(f"/api/research/jobs/{jid}").json()["symbol"] == "ZZT1"
    assert c.post("/api/research/jobs", json={"symbol": "NOPE1"}).status_code == 404
