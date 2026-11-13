-- Live research on demand (item 4). The app writes a job; a worker claims it: the owner's laptop
-- when it is online, otherwise a GitHub Actions run started by the API. Written by the live app,
-- so the Neon mirror's write-back (scripts/neon_http.py) never touches these tables.
CREATE TABLE IF NOT EXISTS research_jobs (
    id            bigserial PRIMARY KEY,
    symbol        text NOT NULL,
    company_id    integer REFERENCES companies(id),
    status        text NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'dispatched', 'running', 'done', 'failed', 'refused')),
    runner        text,                       -- 'laptop' | 'github', set when claimed
    requester     text,                       -- salted hash of the client IP; never the IP itself
    requested_at  timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,                -- when the API asked GitHub to start a runner
    claimed_at    timestamptz,                -- when a worker actually started
    heartbeat_at  timestamptz,
    finished_at   timestamptz,
    steps         jsonb NOT NULL DEFAULT '[]',
    message       text,
    run_url       text
);
-- one live job per symbol: a second request for the same ticker joins the first
CREATE UNIQUE INDEX IF NOT EXISTS research_jobs_one_active
    ON research_jobs (symbol) WHERE status IN ('queued', 'dispatched', 'running');
CREATE INDEX IF NOT EXISTS research_jobs_requester ON research_jobs (requester, requested_at);

-- Laptop worker heartbeat: the API sends work to GitHub only when no worker is online.
CREATE TABLE IF NOT EXISTS workers (
    name      text PRIMARY KEY,
    kind      text NOT NULL,
    last_seen timestamptz NOT NULL DEFAULT now()
);

-- A source that refused a given origin. Permanent: nothing deletes these rows; a person does.
CREATE TABLE IF NOT EXISTS source_blocks (
    origin text NOT NULL,                     -- 'github' (the laptop's record is its marker file)
    source text NOT NULL,                     -- 'NSE'
    at     timestamptz NOT NULL DEFAULT now(),
    detail text,
    PRIMARY KEY (origin, source)
);
